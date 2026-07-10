# AGENTS.md — project instructions for Codex

For general project context, architecture, data layout, and verification, read
`CLAUDE.md`. It is the main maintainer-oriented project guide and applies to
Codex sessions too.

## Image Generation Prompt For Tafsir Filmstrip Backgrounds

Use this prompt contract when generating visual backgrounds for the Quran
tafsir app filmstrip mode. Keep the `SYSTEM` block stable across a batch; vary
only the `PER-TOPIC` block for each topic.

### SYSTEM

```text
Generate a contemplative, cinematic background image for a Quran tafsir app, fullscreen "filmstrip" mode on a phone.

PURPOSE
Inspire reflection on the signs (ayat) of Allah in creation, human life, morality, guidance, trials, mercy, accountability, and the Hereafter — WITHOUT literalizing any sacred or unseen reality. The image supports the meaning of the ayah as a sign, never depicts the sacred itself.

FORMAT & COMPOSITION
Horizontal landscape, aspect ratio 16:9, high resolution. This is the primary format (the app opens the filmstrip in landscape by default).
CENTER-SAFE composition (important): the image may also be shown cropped to a vertical/portrait screen, which cuts off the LEFT and RIGHT edges. Therefore keep the key subject and all essential content within the central safe zone (roughly the middle 60% horizontally). Do not place anything important near the left or right edges.
Keep a calm, uncluttered area in the LOWER-CENTER (sky, water, mist, wall, sand, or open ground) as clean negative space for overlaying Arabic ayah text and a translation, centered so it survives both landscape and portrait. Text must remain readable over it.
Main subject in the upper or central area, off-center but inside the central safe zone; never crowd the bottom-center.

STYLE
Cinematic, naturalistic, atmospheric. Realistic light, depth, quiet grandeur, reflective mood.
Avoid: cartoon, fantasy-game art, horror, kitsch, heavy decoration, generic stock-photo look, HDR over-saturation.
No text, no letters, no numbers, no calligraphy, no script of any language, no symbols, no logo, no watermark, no UI.

RELIGIOUS CONSTRAINTS (hard rules)
- Do NOT depict Allah in any form, and do NOT imply that any light, figure, face, hand, throne, eye, cloud, celestial object, or presence is Allah.
- Do NOT depict any prophet or messenger — no face, no body, no identifiable figure, not even from behind.
- Do NOT depict angels — not as persons, wings, luminous beings, or humanoid forms.
- Do NOT depict Paradise or Hell as literal confirmed realities. Use restrained natural imagery only (gardens, distant light, shade, barren land, distant storm, renewal). Avoid dramatic "hellfire"; if fire is needed, keep it mundane/natural (fading embers, a far lightning storm), never an inferno reading as Hell.
- Do NOT depict manuscripts, scrolls, books, or open pages (the model tends to add fake script). Use light, paths, lanterns, rain on dry earth for revelation/guidance instead.
- No idols as devotional objects, no graphic violence, gore, torture, nudity, or erotic content, nothing disrespectful.
- Avoid mosque-interior / calligraphy clichés unless the topic is specifically worship or prayer, and even then keep it subtle and text-free.

DEPICTION OF LIVING BEINGS (strict default)
- By default show NO people and NO animals up close.
- People are a rare exception, allowed ONLY when the topic cannot read without them. When allowed: distant, small in the frame, back-facing or silhouetted, partially obscured, never with a visible face or portrait detail, never a central heroic figure.
- Animals only distant and incidental, never a portrait.

PREFERRED VISUAL LANGUAGE (signs in creation)
Heavens, stars, dawn, the turning of night and day, rain, clouds, mountains, sea, rivers, plants, seeds, distant landscapes, paths, ruins, flowing water, desert, light after darkness, stillness, vastness, balance, growth, decay and renewal.
For moral/abstract themes use metaphor: crossroads, closed vs open gates, clear vs muddy water, barren vs fertile land, gathering clouds, a distant dawn, footprints, a bridge, a lantern in darkness, calm vs storm, isolation vs shelter.
For disbelief / heedlessness / corruption: shadow, fog, closed doors, distorted reflections, cracked dry earth, storm, isolation — but never horror.

OUTPUT
One polished horizontal 16:9 image, respectful as a background for Quran recitation and tafsir. No embedded words, letters, script, or signatures anywhere in the frame.
```

### PER-TOPIC

```text
TOPIC: <topic name / topic id from the fihrist>

MEANING: <brief semantic description of the ayah/topic, 1-2 lines>

SUGGESTED METAPHOR: <natural/metaphorical image to use>

AVOID FOR THIS TOPIC: <what specifically must not be used for this topic>
```

### Example — Prophet-Related Topic

```text
TOPIC: Musa and the sea

MEANING: Deliverance after oppression; trust; a path opening where none seemed possible.

SUGGESTED METAPHOR: A vast sea at dawn, water receding to suggest a faint dry opening, low light on the horizon. No people in the foreground.

AVOID FOR THIS TOPIC: Do not depict Musa, Pharaoh, any crowd, faces, or the miracle as spectacle. No figures.
```

### Example — Abstract Topic

```text
TOPIC: Guidance after error

MEANING: Light and direction after confusion; mercy that restores.

SUGGESTED METAPHOR: A single path emerging from fog toward a soft distant dawn; rain beginning on cracked dry earth.

AVOID FOR THIS TOPIC: No manuscripts or written pages, no lantern-with-text, no figures.
```

### Usage Notes

- Keep one stable style seed/tail in `SYSTEM` for batch consistency; change only `PER-TOPIC`.
- For topics about Allah's essence/attributes and purely unseen matters, prefer generating no pool at all and let the filmstrip use a neutral background. This is cheaper and safer than filtering many unsuitable images.
- After generation, always review and reject frames with faces, letters/pseudo-script, central figures, or overly literal mystical imagery.
- `16:9` landscape is the primary format. If the service cannot generate exact `16:9`, use the nearest wide ratio such as `3:2`. Keep essential content and overlay text space in the central safe zone so portrait cropping does not cut anything important.
- The filmstrip renders image layers with `background-size: cover`: in landscape most of the frame is visible; in portrait only the central strip remains. This is why center-safe composition is mandatory.
