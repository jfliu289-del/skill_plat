"""Apply versioned taxonomy rules to parsed Skills deterministically."""

import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Set, Tuple

from .models import Classification, ParsedSkill, SourceSpec, Taxonomy


NON_TOKEN = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class _CategoryScore:
    category_id: str
    total: float
    text_total: float
    phrase_score: float


def classify(
    skill: ParsedSkill, taxonomy: Taxonomy, source: SourceSpec
) -> Classification:
    """Classify a parsed Skill using only rules from the supplied taxonomy."""

    searchable_text = _normalize(
        " ".join(
            (
                skill.name,
                skill.description,
                " ".join(skill.headings),
                skill.path.parent.as_posix(),
            )
        )
    )
    tokens = set(searchable_text.split())
    padded_text = f" {searchable_text} "
    reasons: Set[str] = set()
    text_scores: Dict[str, Tuple[float, float]] = {}

    for category_id, category in taxonomy.categories.items():
        matched_phrases = _matched_phrases(category.exact_phrases, padded_text)
        matched_tokens = sorted(set(category.tokens) & tokens)
        phrase_score = (
            len(matched_phrases) * taxonomy.scoring.exact_phrase_weight
        )
        token_score = len(matched_tokens) * taxonomy.scoring.token_weight
        text_scores[category_id] = (phrase_score + token_score, phrase_score)
        reasons.update(
            f"category:{category_id}:phrase:{phrase}" for phrase in matched_phrases
        )
        reasons.update(
            f"category:{category_id}:token:{token}" for token in matched_tokens
        )

    top_text_score = max((score[0] for score in text_scores.values()), default=0.0)
    default_scores: Dict[str, float] = {}
    if top_text_score < taxonomy.scoring.weak_text_threshold:
        for category_id in source.default_categories:
            if category_id in taxonomy.categories:
                default_scores[category_id] = taxonomy.scoring.source_default_weight
                reasons.add(f"source-default:{category_id}")

    ranked = _rank_categories(text_scores, default_scores)
    top = ranked[0]
    if top.total == 0:
        primary_category = taxonomy.scoring.fallback_category
        top = next(
            score for score in ranked if score.category_id == primary_category
        )
        reasons.add(f"fallback:{primary_category}")
    else:
        primary_category = top.category_id

    ranked_others = [
        score for score in ranked if score.category_id != primary_category
    ]
    second_score = ranked_others[0].total if ranked_others else 0.0
    secondary_categories = sorted(
        score.category_id
        for score in ranked_others
        if score.total > 0
        and score.total >= top.total * taxonomy.scoring.secondary_score_ratio
    )

    positive_total = sum(score.total for score in ranked if score.total > 0)
    if top.total == 0 or positive_total == 0:
        confidence = 0.0
        normalized_difference = 0.0
    else:
        evidence_strength = min(
            1.0, top.text_total / taxonomy.scoring.strong_evidence_score
        )
        dominance = top.total / positive_total
        confidence = round(0.6 * evidence_strength + 0.4 * dominance, 4)
        normalized_difference = (top.total - second_score) / top.total

    tags, tag_reasons = _cross_tags(
        taxonomy, padded_text=padded_text, tokens=tokens
    )
    reasons.update(tag_reasons)
    risk_level, risk_reasons = _risk_level(
        taxonomy, padded_text=padded_text, tokens=tokens
    )
    reasons.update(risk_reasons)

    return Classification(
        primary_category=primary_category,
        secondary_categories=secondary_categories,
        tasks=tags["tasks"],
        stages=tags["stages"],
        artifacts=tags["artifacts"],
        domains=tags["domains"],
        audiences=tags["audiences"],
        risk_level=risk_level,
        confidence=confidence,
        needs_review=(
            confidence < taxonomy.scoring.confidence_threshold
            or normalized_difference < taxonomy.scoring.ambiguity_threshold
        ),
        reasons=sorted(reasons),
    )


def _rank_categories(
    text_scores: Dict[str, Tuple[float, float]],
    default_scores: Dict[str, float],
) -> List[_CategoryScore]:
    scores = [
        _CategoryScore(
            category_id=category_id,
            total=text_total + default_scores.get(category_id, 0.0),
            text_total=text_total,
            phrase_score=phrase_score,
        )
        for category_id, (text_total, phrase_score) in text_scores.items()
    ]
    return sorted(
        scores,
        key=lambda score: (-score.total, -score.phrase_score, score.category_id),
    )


def _cross_tags(
    taxonomy: Taxonomy, padded_text: str, tokens: Set[str]
) -> Tuple[Dict[str, List[str]], Set[str]]:
    tags = {
        "tasks": set(),
        "stages": set(),
        "artifacts": set(),
        "domains": set(),
        "audiences": set(),
    }
    reasons = set()
    for rule in taxonomy.cross_tag_rules:
        if not _rule_matches(rule.exact_phrases, rule.tokens, padded_text, tokens):
            continue
        reasons.add(f"cross-tag:{rule.id}")
        for name in tags:
            tags[name].update(getattr(rule, name))
    return {name: sorted(values) for name, values in tags.items()}, reasons


def _risk_level(
    taxonomy: Taxonomy, padded_text: str, tokens: Set[str]
) -> Tuple[str, Set[str]]:
    highest = 0
    reasons = set()
    for cue in taxonomy.risk_cues:
        if not _rule_matches(cue.exact_phrases, cue.tokens, padded_text, tokens):
            continue
        level = int(cue.level[1:])
        highest = max(highest, level)
        reasons.add(f"risk:{cue.level}")
    return f"R{highest}", reasons


def _rule_matches(
    exact_phrases: Iterable[str],
    rule_tokens: Iterable[str],
    padded_text: str,
    tokens: Set[str],
) -> bool:
    return bool(_matched_phrases(exact_phrases, padded_text)) or bool(
        set(rule_tokens) & tokens
    )


def _matched_phrases(
    exact_phrases: Iterable[str], padded_text: str
) -> List[str]:
    return sorted(
        phrase
        for phrase in exact_phrases
        if f" {_normalize(phrase)} " in padded_text
    )


def _normalize(value: str) -> str:
    return " ".join(NON_TOKEN.sub(" ", value.lower()).split())
