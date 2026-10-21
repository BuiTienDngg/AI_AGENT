# Task: Translate the final, approved American English game article to Vietnamese

Read `article.json` — it is the SINGLE authoritative source article. Translate ONLY AFTER the English article has passed all editorial QA. Preserve the existing article data structure, returning the exact JSON object shape specified by translation.schema.json.

Translate all public-facing content (meta_title, meta_description, article paragraphs, and subsection headings) into **natural, publishable Vietnamese**, written as a professional Vietnamese game publisher. The output must not be a new interpretation, rewritten research, fresh creative story, or additional source of claims; it is a faithful EN-to-VI translation. Keep the game title `title` EXACTLY unchanged. Never ask the user for cultural inspiration.

Follow writing_style.md. Translate the meaning and action in natural spoken Vietnamese, not English sentence order or word-for-word metaphors. Rebuild each sentence within its existing paragraph so a new player understands the object, action, rule and result immediately. Prefer consistent everyday terms such as khối hình, bàn chơi, ô trống, hàng ngang, cột dọc, kéo, thả and xóa hàng/cột. Avoid calques like 'hình chữ nhật gọn' or 'hướng việc đặt'. Keep the same factual scope; lively language must not invent a sound, animation or mechanic. Read the Vietnamese paragraph aloud before returning it.

Read brand_context.json. Preserve the source's official first-person developer stance: `we` -> `chúng tôi`, `our game` -> `trò chơi của chúng tôi`, and `we developed/designed` -> `chúng tôi phát triển/thiết kế` where present. Keep the causal thread from the opening's real-world context to our creative concept and design choices. Do not turn the translation into an outsider's review or add hedging about owner-confirmed authorship.

REQUIRED six top-level headings, verbatim and in the same order:
1. Concept and Inspiration -> Ý tưởng và cảm hứng
2. Story -> Cốt truyện
3. Gameplay -> Lối chơi
4. Visual Style -> Phong cách hình ảnh
5. Standout Features -> Điểm nổi bật
6. Controls -> Điều khiển

Invariant checks (STRICT):
- Same number/order of sections, subsections and paragraphs as article.json.
- Preserve every `[[SRC###]]` token in the SAME paragraph and SAME ORDER. Never invent, delete, renumber or translate IDs, links or citation tokens.
- Preserve every paragraph's `image_ids` array EXACTLY and in identical order. Do not add or remove images. Python generates the same References/credits from registries.
- Translate every image_captions.caption into natural Vietnamese while preserving its image_id and sequence exactly. Use [] for paragraphs with no captions. Caption text describes the same illustration as EN, with no new factual claims. If the source is a legacy draft without image_captions, return [] and let Python use the translated nearest H3/H2.
- Preserve gameplay facts, control keys, proper nouns, figures and source meaning; do not add unsupported facts or omit meaningful details.
- Do not introduce new claims based on translator intuition. Translate American-English publisher prose into clear Vietnamese rather than mechanical literal wording.
- Keep technical names and visible game text in English when they are official UI labels (e.g., PLAY, Score), explaining in Vietnamese as appropriate.
- All translated values must be valid JSON strings; no Markdown outside the JSON object.

Only write the JSON translation as prescribed by the schema. Codex CLI will save it to translation_vi.json.
