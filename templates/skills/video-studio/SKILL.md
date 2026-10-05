# Synapse Video Director

Use this skill whenever a user wants an AI-generated video, especially a multi-scene video, a recurring character, dialogue, a coherent narrative, or anything longer than one provider-native short clip.

## Goal

Treat Synapse Video Studio as a **director + continuity + render + assembly system**, not as a single prompt box. The quality target is a video that makes narrative and visual sense from beginning to end, keeps recurring people/objects/locations recognizable, maintains state across cuts, and uses audio intentionally.

## Core rule

**Do not ask a video model to improvise an entire minutes-long film from disconnected prompts.**

Instead:

1. Resolve the creative brief.
2. Build one story bible.
3. Build one character/identity bible.
4. Build one visual/style bible.
5. Break the film into ordered 3–10 second beats.
6. Put consecutive beats that truly share scene state into one `continuity_group` of at most 40 seconds.
7. Use stable project reference images for recurring people, products, costumes, creatures, props, or locations when available.
8. Give dialogue and sound design explicitly.
9. Create the plan with `synapse_create_video_plan`.
10. Render with `synapse_start_video_render`.
11. Poll `synapse_get_video_job` until terminal state; do not restart an already-running render just because it is slow.
12. Inspect the completed asset/provenance with `synapse_get_video_asset` or `synapse_audit_video_assets`.

Synapse handles provider-native short generation, stateful extension inside continuity groups, last-frame bridging across groups, local MP4 assembly, and provenance.

## Story bible

Write concise facts that must remain true across the whole video:

- Who is the protagonist and what do they want?
- What happened immediately before the film begins?
- Beginning → escalation → payoff/resolution.
- Time of day and chronology.
- Location relationships.
- Important props and who has them.
- What information each character knows at each point.
- Emotional progression.

Do not fill the story bible with camera language. It is world/state memory.

## Character bible

For every recurring person/creature, specify identity anchors that should not drift:

- stable name/role
- approximate age presentation when relevant
- face/hair/skin/fur defining features
- body proportions/build
- wardrobe and accessories
- voice qualities/accent/register if dialogue is needed
- movement habits
- emotional baseline
- forbidden identity changes

When the user provides a reference image, use its project-relative path in `reference_paths`. Do not claim an exact real-person likeness can be preserved unless the provider permits that use and the user has the right/consent to use the image.

## Style bible

Lock the visual grammar:

- realism/stylization level
- lens/camera language
- lighting and contrast
- color treatment
- texture/film grain
- motion style
- depth of field
- production design
- aspect ratio intent

Keep style consistent unless the story deliberately changes it.

## Shot design

Each shot should communicate **one beat**. Strong shot prompts state:

- what is already true at the start
- who is present
- what action happens
- the camera behavior
- what must remain unchanged
- what changes by the end

Avoid contradictory prompts and unnecessary subject re-description inside the same continuity group. The group already carries prior state.

### Continuity groups

Use the same `continuity_group` when the video should feel like one stateful scene or a direct continuation. Keep each group at **40 seconds or less**.

Start a new continuity group for:

- a significant time jump
- a major location change
- a montage with intentionally independent moments
- a new visual grammar
- a story chapter that should not inherit the exact previous scene state

Groups must be contiguous in the plan. Never use group A, then group B, then return to A.

## Audio and dialogue

Default to `audio_mode="native"` when sound helps the video.

For dialogue:

- Put the exact intended line in `dialogue`.
- Use short, speakable lines that fit the shot duration.
- Keep the same character's vocal description in the character bible.
- Do not overload an 8-second shot with a paragraph of speech.

For sound:

- Put recurring ambience/music state in the story/style bible when it persists.
- Put shot-specific changes in `audio_cues`.
- Describe transitions: music continues, ambience fades, door slam interrupts silence, etc.

Use `audio_mode="silent"` only when the user wants no generated sound or when another audio post-production lane is intentionally planned.

## Long-form pacing

A five-minute maximum is 300 seconds, but do not target 300 seconds unless the content warrants it. Plan for rhythm rather than filling time.

Useful pattern for a narrative video:

- Establishment: 10–30s
- Setup: 30–60s
- Development: 60–150s
- Escalation/payoff: 30–90s
- Resolution/end card: 10–30s

This is guidance, not a mandatory template.

## Reference-image workflow

When recurring identity matters and no reference asset exists, consider creating a clean reference image with Synapse Image Studio first. Favor a neutral, well-lit reference showing the subject clearly. Use multiple references only when each adds a distinct needed fact; too many conflicting references can reduce consistency.

## Quality-control loop

After a render completes:

1. Confirm the final MP4 exists and provenance hash verifies.
2. Compare actual duration with planned duration.
3. Review story order and scene transitions.
4. Check recurring character/product identity at every chapter boundary.
5. Check wardrobe/prop/location continuity.
6. Check lip/dialogue plausibility and voice consistency.
7. Check audio continuity across scene boundaries.
8. Check for sudden unexplained subjects, geometry, text, or background changes.

If a section is weak, prefer a **targeted re-plan/re-render** of the affected continuity block over regenerating the entire movie. Preserve the original plan and references so the repair remains controlled.

## MCP tool sequence

Readiness:

`Synapse.synapse_video_generation_status`

Create a project-scoped plan:

`Synapse.synapse_create_video_plan`

Start rendering:

`Synapse.synapse_start_video_render`

Track durable progress:

`Synapse.synapse_get_video_job`

Cancel cooperatively if the user requests it:

`Synapse.synapse_cancel_video_render`

Inspect final provenance:

`Synapse.synapse_list_project_videos`
`Synapse.synapse_get_video_asset`
`Synapse.synapse_audit_video_assets`

## Failure behavior

- If provider credentials are missing, do not invent a render result. Report that the plan can still be prepared but provider-backed rendering is not configured.
- If the assembler is unavailable, do not claim the minutes-long final MP4 was created.
- If a provider rejects one shot, surface the failing shot/group and keep prior completed artifacts; do not silently restart the entire film.
- If a render job is already running, poll its durable job id instead of launching duplicates.
- Never expose API keys in prompts, logs, plans, or user-visible status.

## Rights, likeness, and provenance

Only use media the user is entitled to use. Keep Synapse's project-scoped provenance records intact. Do not strip provider provenance/watermarks or misrepresent generated footage as authentic documentary evidence.
