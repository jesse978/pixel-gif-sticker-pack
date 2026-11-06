EXPRESSIONS = [
    {"id": "happy", "name": "开心", "caption": "开心到起飞", "emoji": "✦", "action": "laughing joyfully with closed crescent eyes, raising both hands in celebration"},
    {"id": "ok", "name": "收到", "caption": "收到！", "emoji": "✓", "action": "confidently giving a thumbs up, with a warm closed-mouth smile"},
    {"id": "love", "name": "比心", "caption": "爱你哟", "emoji": "♡", "action": "making a heart with both hands at chest level, smiling with affection"},
    {"id": "cry", "name": "委屈", "caption": "委屈巴巴", "emoji": "◡", "action": "looking adorably upset, with large tears, drooping brows and a small pouting mouth"},
    {"id": "tired", "name": "躺平", "caption": "不想上班", "emoji": "zZ", "action": "exhausted, half-closed sleepy eyes, resting their cheek on one hand"},
    {"id": "shock", "name": "震惊", "caption": "真的假的", "emoji": "!", "action": "surprised, with widened eyes and an open O-shaped mouth, palms beside the cheeks"},
    {"id": "angry", "name": "生气", "caption": "哼！", "emoji": "≋", "action": "playfully annoyed, puffed cheeks, arms crossed, furrowed brows"},
    {"id": "cheer", "name": "加油", "caption": "冲鸭！", "emoji": "↗", "action": "raising a fist enthusiastically in encouragement, determined happy eyes"},
    {"id": "bye", "name": "挥手", "caption": "先溜啦", "emoji": "⌁", "action": "waving goodbye with one hand, relaxed friendly grin"},
    {"id": "think", "name": "思考", "caption": "让我想想", "emoji": "?", "action": "tilting the head and holding the chin, one eyebrow raised in thought"},
    {"id": "thanks", "name": "感谢", "caption": "谢谢老板", "emoji": "✿", "action": "clasping both hands together to say thanks, beaming with gratitude"},
    {"id": "awkward", "name": "尴尬", "caption": "尴尬而礼貌", "emoji": "…", "action": "an awkward polite smile, one small sweat drop near the temple"},
]
BY_ID = {x["id"]: x for x in EXPRESSIONS}
STYLES = {
    "real": "Photorealistic cutout sticker, maintaining the person's real facial structure and realistic skin texture. Keep the same age, hairstyle, hair color, skin tone, distinguishing facial features, glasses, and outfit.",
    "chibi": "Tasteful expressive hand-drawn chibi sticker illustration, soft flat colors, bold clean outlines. Stylize proportions while retaining recognizable hairstyle, hair color, face shape, eyebrows, glasses, skin tone, and clothing from the reference. Do not substitute a generic character.",
    "pixel": "Expressive pixel-art character sticker, deliberate crisp square pixels, limited harmonious color palette. Retain recognizable hair silhouette and color, face shape, glasses, skin tone, and outfit of the reference person.",
}
