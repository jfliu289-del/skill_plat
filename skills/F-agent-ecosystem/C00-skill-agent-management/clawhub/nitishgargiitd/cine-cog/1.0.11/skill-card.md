## Description: <br>
Cine Cog guides agents in using CellCog to produce cinematic AI videos such as short films, music videos, brand films, and widescreen visual stories from prompts. <br>

This skill is ready for commercial/non-commercial use. <br>

## Publisher: <br>
[nitishgargiitd](https://clawhub.ai/user/nitishgargiitd) <br>

### License/Terms of Use: <br>
MIT-0 <br>


## Use Case: <br>
External users, developers, and creative teams use this skill to prompt CellCog for cinematic video concepts, scene plans, brand films, music videos, short films, and related AI video generation workflows. <br>

### Deployment Geography for Use: <br>
Global <br>

## Known Risks and Mitigations: <br>
Risk: The skill requires a CellCog API key and use of the CellCog Python package. <br>
Mitigation: Install only when CellCog is intended for the workflow, store CELLCOG_API_KEY in the agent environment, and avoid exposing the key in prompts or generated files. <br>
Risk: Creative prompts or attached material may be sent to the CellCog service. <br>
Mitigation: Do not include secrets, confidential unreleased content, or rights-sensitive material unless CellCog account controls and data policies meet the user's requirements. <br>
Risk: Cinematic video generation may consume credits or billing resources without guaranteeing a satisfactory output. <br>
Mitigation: Monitor CellCog credit or billing usage and start with smaller prompts or shorter scenes before requesting long-form cinematic work. <br>
Risk: Generated cinematic outputs can be unpredictable in quality or suitability. <br>
Mitigation: Review generated results before production use and iterate prompts with explicit scene, style, format, and music direction. <br>


## Reference(s): <br>
- [CellCog homepage](https://cellcog.ai) <br>
- [ClawHub skill page](https://clawhub.ai/nitishgargiitd/skills/cine-cog) <br>


## Skill Output: <br>
**Output Type(s):** [Guidance, Code, Shell commands, Configuration] <br>
**Output Format:** [Markdown with Python and shell code blocks] <br>
**Output Parameters:** [1D] <br>
**Other Properties Related to Output:** [Requires python3, CELLCOG_API_KEY, the CellCog Python package, and a CellCog account; generated results are returned through the CellCog service.] <br>

## Skill Version(s): <br>
1.0.11 (source: server release metadata) <br>

## Ethical Considerations: <br>
Users should evaluate whether this skill is appropriate for their environment, review any generated or modified files before relying on them, and apply their organization's safety, security, and compliance requirements before deployment. <br>
