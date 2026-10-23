# Slope3: clear, natural game writing

Write like a game developer explaining the game to a new player sitting beside them. The reader should be able to picture the screen and understand the next action after one reading.

## Priorities

1. Explain verified actions and rules clearly.
2. Make the prose friendly and pleasant to read aloud.
3. Keep the official Slope3 voice and a coherent creative concept.
4. Add relevant background and citations where they help.

The concept connects the article; it does not need to be restated in every paragraph. In Gameplay and Controls, a direct explanation of play takes priority over discussion of our design intentions.

## Write actions readers can picture

- Use familiar nouns: block, board, empty cell, row, column, train, barrier, coin. Choose one consistent name for each object. Distinguish a whole block shape from the smaller cells it occupies.
- Prefer verbs: pick up, drag, drop, fill, clear, jump, dodge, collect. Name what the player moves, where it goes, and what happens next.
- Explain a rule as action -> condition -> visible result. State the core loop early in Gameplay before discussing strategies, visual details or theory.
- Use a small concrete example when a rule is easier to show than describe. Do not invent board dimensions, scores, piece rotation, failure conditions or device controls to make the example work.
- Keep most sentences short enough to say comfortably in one breath. Vary the rhythm naturally. No fixed sentence-length score and no padding to meet a word count.
- A little playfulness is welcome. One brief "Pop!" or "Bùm!" can describe the moment a line clears; it is not evidence of an actual recorded sound or explosion effect. Do not turn every paragraph into hype.
- Remove sentences that merely announce a relationship, question, intention or experience without explaining it. Phrases such as "spatial demands", "the relationship between available shapes and the arrangement", or "direct its placement" hide the action the reader needs.
- Group minor interface details into a useful sentence. Explain a symbol's role only when confirmed and helpful to the player; keep exhaustive lists of unexplained icons in the private inventory.

## Section jobs

- **Concept and Inspiration:** start with a relevant, easy-to-imagine real-world idea, then explain how it led to our game. Keep research readable. Do not force an unrelated study or second metaphor into the article to fill a citation quota.
- **Story:** give an engaging premise where appropriate. For an abstract puzzle, a short player situation can be enough. Do not manufacture elaborate lore or describe the board as a conversation, composition or philosophical journey to fill space.
- **Gameplay:** a newcomer should learn what they control/place, the main rule, and the result. Then explain useful objects, challenges, scoring or endings that are actually confirmed.
- **Visual Style:** name visible colors, shapes and screen elements and explain how they help the player see or understand the game. Avoid abstract claims about a visual vocabulary or spatial framework.
- **Standout Features:** explain concrete features and why they are enjoyable or useful. Do not repeat the introduction or turn each feature into a statement about our concept.
- **Controls:** tell the reader the actual confirmed gesture, button or key and its result. Placement strategy is not a substitute for operating instructions. Use owner-confirmed controls in game_objects.json even if a still image could not prove them. If controls truly remain unknown, keep the question private and do not invent them.

## Before / after

Opaque: "Straight bars, compact rectangles, squares, and bent shapes create different spatial demands."
Clear: "The blocks come in different shapes. Some need a long gap; others fit into a corner. Check the empty cells before choosing where to put each block."

Opaque: "Identify a piece, compare its complete outline with the grid, and direct its placement toward a suitable open area."
Clear, only when drag/drop is confirmed: "Pick up a block from below the board, drag it to an empty space, and release it to place it."

Owner-provided Block Blast example, only for a product with these confirmed rules:
"Drag a block onto the board and drop it into the empty cells. Fill a whole horizontal row or vertical column and—pop!—that line disappears, making room for your next blocks."

Natural Vietnamese for the same confirmed rules:
"Chọn một khối hình, kéo vào chỗ trống trên bàn chơi rồi thả tay. Lấp kín một hàng ngang hoặc một cột dọc là bùm! Hàng hoặc cột đó biến mất, nhường chỗ cho những khối tiếp theo."

These examples teach a writing style. Do not copy block-puzzle mechanics into another game.

## Vietnamese translation

- Preserve facts, paragraph boundaries, citations, images and developer voice. Rebuild the sentences in natural Vietnamese; do not copy English word order or every metaphor.
- Use familiar game words consistently: khối hình, bàn chơi, ô trống, hàng ngang, cột dọc, kéo, thả, lấp kín, xóa hàng/cột.
- Do not translate "compact rectangles" as "hình chữ nhật gọn". Use a clear shape description supported by evidence, or flag the EN source for clarification.
- Avoid calques such as "định hướng việc đặt", "yêu cầu về không gian" or "bố cục đang biến đổi" when the actual meaning is simply placing a block, finding a gap or clearing a line.
- Read the paragraph aloud. If a player would ask "What am I supposed to do?" or "What does that shape mean?", rewrite it before approving.

## Editorial gate

Treat an incomprehensible main rule, vague confirmed control, undefined object description, or unreadable translation as a blocking error, not a minor style warning. A correct fact or valid citation does not make an opaque sentence acceptable. Minor preferences remain warnings.

For each problem, identify the exact paragraph and propose a concrete replacement using confirmed facts. Keep citations and media intact. Do not repair unclear writing by adding an unverified mechanic.
## Section-specific tone and completeness

Concept and Inspiration may be more lyrical and gentle than the instructional sections. Ground a small evocative image in sourced context, connect it to our creative idea and a concrete design choice, and end with the experience we intend to create. Carry an idea naturally between paragraphs. No ornamental fog, abrupt research digressions or invented studio history.

Gameplay must help a newcomer understand the objective, how to succeed, the actual rewards, what ends the game and what happens after losing. An endless score game may have no final victory; confirm that rather than inventing one. Unknown rules require owner clarification, not assumptions. Keep gameplay and controls concrete even when the concept is poetic.

Standout Features explains a specific supported difference and why it matters to the player. Distinguish visual 3D depth from mechanical layers or rotation. A generic 2D comparison can explain presentation; factual claims about a named competing game require evidence. Describe intended appeal naturally without asserting unmeasured superiority.

## Controls: teach a first-time player

Write Controls as a short practical walkthrough, with PC and Mobile subsections when both are supported. Start with the device and exact confirmed input. Explain where the player acts, whether to press, hold or release, which direction to move, and what happens on screen. Use a simple sequence the reader can perform on their first turn; connect it briefly to the objective explained in Gameplay.

For keyboard play, name each confirmed key and its exact action, distinguishing a tap from holding only when known. For mouse play, name the confirmed mouse button, target, drag direction and release action. For touch play, distinguish tapping, holding, dragging, swiping and lifting the finger. Do not replace inputs with strategy such as planning space or reacting quickly. Do not copy the owner's long control notes verbatim; turn them into concise, natural instructions without changing their meaning.

For an owner-confirmed drag-and-drop block game, a useful PC sequence is: move the pointer onto a block below the board, hold the left mouse button, drag the block over a suitable empty space and release the button to place it. The corresponding mobile sequence is: touch and hold a block, drag it with your finger onto the board, then lift your finger to place it. Use these details only when confirmed for this product. Add the confirmed clear-line result briefly so readers understand why they are placing blocks.

Never add arrow keys, WASD, Space, right-click, rotation, pinch gestures, restart shortcuts, touch zones or unsupported platforms from genre conventions. A mouse-controlled game need not have keyboard mappings. If a necessary input is missing, ask the owner during analysis/notes instead of guessing. A new player should finish this section knowing exactly how to begin playing.

