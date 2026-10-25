"""nekosapi 数据源标签词典。

该源是英文标签体系，实测采样 600 张图共发现 44 个标签，规模远小于 Pixiv。
这里建立中文 -> 英文的映射，并补充 Pixiv 常用词到该源的对应关系。
"""

# 该源实际存在的标签（采样 600 张得出，按频率排序）
# 标 * 的为敏感标签，仅用于黑名单识别，不作为用户可输入标签对外展示
SOURCE_TAGS = [
    "girl", "skirt", "black_hair", "dress", "flowers", "kemonomimi",
    "pink_hair", "gloves", "brown_hair", "school_uniform", "blonde_hair",
    "tree", "maid", "blue_hair", "beach", "red_hair", "night",
    "purple_hair", "shorts", "catgirl", "bikini", "mountain", "wet",
    "weapon", "rain", "white_hair", "plants", "sunny", "boy", "glasses",
    "usagimimi", "sword", "yuri", "sportswear", "guitar", "horsegirl",
    "bunny_girl", "illustration",
]

# 敏感标签黑名单：出现在图片标签里则跳过
SENSITIVE_TAGS = {
    "exposed_girl_breasts", "large_breasts", "medium_breasts", "small_breasts",
    "breasts", "exposed_breasts", "nipples", "nude", "naked", "pussy",
    "dick", "penis", "anus", "exposed_anus", "cum", "sex", "futanari",
    "explicit", "uncensored", "spread_legs", "underwear_only",
}

# 中文 -> 该源标签
ALIASES = {
    # 服装
    "女仆": "maid", "女仆装": "maid", "女仆服": "maid",
    "裙子": "skirt", "短裙": "skirt", "连衣裙": "dress", "礼服": "dress",
    "校服": "school_uniform", "制服": "school_uniform", "水手服": "school_uniform",
    "手套": "gloves", "短裤": "shorts", "泳装": "bikini", "比基尼": "bikini",
    "运动服": "sportswear", "眼镜": "glasses",

    # 兽耳
    "兽耳": "kemonomimi", "猫耳": "catgirl", "猫娘": "catgirl",
    "兔耳": "usagimimi", "兔女郎": "bunny_girl", "兔娘": "usagimimi",
    "马娘": "horsegirl",

    # 发色
    "黑发": "black_hair", "粉发": "pink_hair", "棕发": "brown_hair",
    "茶发": "brown_hair", "金发": "blonde_hair", "蓝发": "blue_hair",
    "红发": "red_hair", "紫发": "purple_hair", "白发": "white_hair",

    # 场景
    "花": "flowers", "花朵": "flowers", "树": "tree", "树木": "tree",
    "海滩": "beach", "海边": "beach", "沙滩": "beach",
    "夜晚": "night", "夜间": "night", "山": "mountain",
    "雨": "rain", "雨天": "rain", "晴天": "sunny",
    "植物": "plants", "晴天户外": "sunny",

    # 其他
    "少女": "girl", "女孩": "girl", "女孩纸": "girl",
    "少年": "boy", "男孩": "boy",
    "湿身": "wet", "武器": "weapon", "剑": "sword", "刀剑": "sword",
    "百合": "yuri", "吉他": "guitar", "插画": "illustration",
}

# 分类展示
# 各标签的实际图量（2026-10 实测 rating=safe 条件下），用于标注热度
TAG_COUNTS = {
    "girl": 14649, "skirt": 2965, "black_hair": 2179, "dress": 1958,
    "flowers": 1762, "brown_hair": 1657, "blonde_hair": 1526,
    "gloves": 1488, "school_uniform": 1402, "kemonomimi": 1282,
    "pink_hair": 1240, "tree": 1003, "night": 902, "blue_hair": 786,
    "bikini": 733, "beach": 660, "boy": 602, "maid": 597,
    "red_hair": 571, "weapon": 571, "purple_hair": 572, "shorts": 480,
    "wet": 426, "white_hair": 404, "mountain": 400, "plants": 367,
    "sunny": 328, "catgirl": 321, "sword": 273, "glasses": 258,
    "rain": 257, "usagimimi": 163, "yuri": 143, "guitar": 60,
    "bunny_girl": 45, "sportswear": 29, "horsegirl": 23,
    "illustration": 16,
}

GROUPS = [
    ("人物", {"girl": "少女", "boy": "少年"}),
    ("服装", {"maid": "女仆", "skirt": "短裙", "dress": "连衣裙",
              "school_uniform": "制服", "gloves": "手套", "shorts": "短裤",
              "bikini": "泳装", "sportswear": "运动服", "glasses": "眼镜"}),
    ("兽耳", {"kemonomimi": "兽耳", "catgirl": "猫娘", "usagimimi": "兔耳",
              "bunny_girl": "兔女郎", "horsegirl": "马娘"}),
    ("发色", {"black_hair": "黑发", "blonde_hair": "金发", "brown_hair": "棕发",
              "pink_hair": "粉发", "blue_hair": "蓝发", "red_hair": "红发",
              "purple_hair": "紫发", "white_hair": "白发"}),
    ("场景", {"flowers": "花", "tree": "树", "plants": "植物", "beach": "海滩",
              "night": "夜晚", "mountain": "山", "rain": "雨", "sunny": "晴天"}),
    ("其他", {"wet": "湿身", "weapon": "武器", "sword": "剑", "yuri": "百合",
              "guitar": "吉他", "illustration": "插画"}),
]

TOTAL_TAGS = len(ALIASES)


# 反向映射：英文标签 -> 中文名
REVERSE = {}
for _name, _group in GROUPS:
    for _en, _cn in _group.items():
        REVERSE[_en] = _cn


def heat(count):
    """把图量转成直观的热度标识。"""
    if count is None:
        return ""
    if count >= 1000:
        return "🔥"
    if count >= 300:
        return "★"
    if count >= 100:
        return "·"
    return "△"
