import os
import re
import sqlite3
from datetime import datetime, timedelta
from typing import Optional, Tuple, Dict, Any, List

from astrbot.api.star import Context, Star, register
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api import AstrBotConfig
from astrbot.api.message_components import Plain
from astrbot.api.web import error_response, json_response, request
from astrbot.api import logger


# ========== 插件常量 ==========
PLUGIN_NAME = "astrbot_plugin_lie_detector"
PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
# 数据存储于 AstrBot data/plugin_data/ 目录，防止插件更新时数据丢失
DATA_DIR = os.path.join(os.path.dirname(PLUGIN_DIR), "data", "plugin_data", PLUGIN_NAME)
DB_PATH = os.path.join(DATA_DIR, "lie_detector.db")

DEFAULT_PROMPT = (
    "你是一个专业的查证专家。请分析以下发言的可信度，并给出0-100的评分（可以是小数，如72.5）。\n\n"
    "发言内容：{message}\n\n"
    "【核心评估原则】\n"
    "1. 事实正确性（最重要）：\n"
    "   - 数学、逻辑、科学事实（如'1+1=2''地球是圆的''水在0度结冰'）→ 90-100分\n"
    "   - 常识性正确事实（如'地球上有水''太阳会发光'）→ 80-100分\n"
    "   - 明显虚假或荒谬的内容（如'月亮是奶酪做的''1+1=3'）→ 0-20分\n"
    "   - 无法验证的个人经历或观点 → 40-60分\n"
    "   - 部分真实但部分可疑 → 30-50分\n\n"
    "2. 不当内容识别（必须优先处理）：\n"
    "   - 涉黄/色情内容 → 0分，理由：'内容涉及不当信息'\n"
    "   - 故意歪曲他人信息（如明知对方性别却故意说错）进行侮辱 → 0-10分，理由：'恶意篡改事实，侮辱他人'\n"
    "   - 人身攻击/辱骂性内容 → 10-20分，理由：'包含攻击性语言'\n"
    "   - 歧视性言论（性别歧视、种族歧视等）→ 10-20分，理由：'包含歧视性内容'\n"
    "   - 这类内容即使'逻辑自洽'也必须给低分\n\n"
    "3. 简短但正确的内容应该得到高分：\n"
    "   - 即使内容很短（如'1+1''对''是的'），只要客观正确就应该给80分以上\n"
    "   - 不要因为'缺乏细节'就否定正确的事实\n\n"
    "4. 极简短的肯定/否定词（如'是''不是''对''不对''嗯''哦'）：\n"
    "   - 这类词无法独立判断真伪，给50-60分（存疑）\n"
    "   - 理由说明：'简短回应，无法独立验证真伪'\n"
    "   - 不要因为内容短就给0分，也不要因为可能是正确回应就给高分\n\n"
    "5. 语言风格（辅助参考）：\n"
    "   - 绝对化表述（'绝对''肯定'）：如果内容正确，不扣分；如果可疑，额外扣10-20分\n"
    "   - 模糊化表述（'可能''也许'）：诚实的不确定轻微扣分；逃避责任扣5-15分\n"
    "   - 夸张/煽动性语言：扣10-25分\n\n"
    "6. 逻辑自洽性：\n"
    "   - 有自相矛盾：扣15-30分\n"
    "   - 逻辑清晰：加5-10分\n\n"
    "【示例】\n"
    "- '1+1' → 90-100分（数学事实，简短但正确）\n"
    "- '2024年的地球上绝对有水' → 90-100分（常识性正确事实）\n"
    "- '是' → 50-60分（简短肯定词，无法独立验证）\n"
    "- '不是' → 50-60分（简短否定词，无法独立验证）\n"
    "- '对' → 50-60分（简短肯定词，无法独立验证）\n"
    "- '我昨天吃了3个苹果' → 70-80分（普通陈述，有细节）\n"
    "- '月亮是用奶酪做的' → 0-10分（明显虚假）\n"
    "- '1+1=3' → 0-10分（数学错误）\n"
    "- '我可能中了一百万彩票' → 40-50分（无法验证，模糊表述）\n"
    "- '这个产品百分百有效，包治百病' → 10-20分（夸张+虚假）\n"
    "- 'xxx是个变态/色情内容' → 0-10分（人身攻击/不当内容）\n"
    "- '某某明明是男生却说是女生' → 0-10分（恶意歪曲事实）\n\n"
    "请严格按照以下格式输出，不要添加任何额外内容：\n"
    "评分：[0-100的数字，可以是小数]\n"
    "结论：[可信/基本可信/存疑/可疑/虚假]\n"
    "理由：[详细的分析理由，不超过80字]"
)

ICON_MAP = {
    "credible": "🟢",
    "reliable": "🟡",
    "doubtful": "🟠",
    "suspicious": "🔴",
    "false": "💀",
}

ABSOLUTE_WORDS = [
    "绝对", "肯定", "一定", "必然", "百分之百", "100%", "毫无疑问",
    "毋庸置疑", "完全", "全部", "所有", "从来", "永远", "根本",
    "绝对不会", "绝对是", "完全是", "肯定是", "一定是",
]

VAGUE_WORDS = [
    "大概", "可能", "也许", "差不多", "应该", "好像", "似乎",
    "或许", "估计", "听说", "据说", "据说是", "有人说", "大概是",
    "差不多吧", "应该是", "好像是",
]

ABSURD_WORDS = [
    "震惊", "难以置信", "你绝对不会相信", "史上最", "全世界最",
    "一夜暴富", "月入百万", "零成本", "免费午餐", "无风险",
    "稳赚不赔", "百分百成功", "包过", "包治", "万能",
]

# 常识性事实词（用于降低绝对化表述的惩罚）
COMMON_SENSE_WORDS = [
    "地球", "太阳", "月亮", "水", "空气", "氧气", "重力", "引力",
    "春夏秋冬", "四季", "白天", "黑夜", "生老病死", "吃饭", "喝水",
    "睡觉", "走路", "说话", "看得见", "听得到", "摸得着",
    "1+1=2", "2+2=4", "三角形", "圆形", "方形",
]

EMOTION_WORDS = [
    "气死了", "笑死", "崩溃", "破防", "无语", "离谱", "疯了",
    "哭了", "笑哭", "太棒了", "绝了", "逆天", "恐怖", "可怕",
]

FIRST_PERSON_WORDS = [
    "我亲眼", "我亲自", "我经历", "我看到", "我听到", "我感受",
    "我当时", "我那天", "我昨天", "我上次",
]

CONTRADICT_WORDS = [
    "但是", "不过", "然而", "其实", "实际上", "说实话",
    "不瞒你说", "坦白讲", "客观来说",
]


# ========== 本地 SQLite 数据库管理 ==========
class DatabaseManager:
    def __init__(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        self.conn = sqlite3.connect(DB_PATH)
        self.conn.row_factory = sqlite3.Row
        self._init_tables()

    def _init_tables(self):
        c = self.conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                user_name TEXT DEFAULT '',
                avg_score REAL DEFAULT 0,
                total_checks INTEGER DEFAULT 0,
                daily_count INTEGER DEFAULT 0,
                last_check_date TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS checks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                score REAL,
                level TEXT,
                reason TEXT,
                message_preview TEXT,
                source_group TEXT DEFAULT '',
                created_at TEXT
            )
        """)
        # 违规记录表
        c.execute("""
            CREATE TABLE IF NOT EXISTS violations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                group_id TEXT,
                violation_type TEXT,
                message_content TEXT,
                created_at TEXT
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_violations_user ON violations(user_id)")
        # 兼容旧表：如果 source_group 列不存在则添加
        try:
            c.execute("ALTER TABLE checks ADD COLUMN source_group TEXT DEFAULT ''")
        except Exception:
            pass  # 列已存在
        c.execute("CREATE INDEX IF NOT EXISTS idx_checks_user ON checks(user_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_checks_date ON checks(created_at)")
        self.conn.commit()

    def add_violation(self, user_id: str, group_id: str, violation_type: str, message_content: str) -> int:
        """添加违规记录，返回违规次数"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c = self.conn.cursor()
        c.execute(
            "INSERT INTO violations (user_id, group_id, violation_type, message_content, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, group_id, violation_type, message_content[:200], now),
        )
        self.conn.commit()
        # 统计该用户在该群的违规次数
        c.execute(
            "SELECT COUNT(*) as cnt FROM violations WHERE user_id = ? AND group_id = ?",
            (user_id, group_id),
        )
        return c.fetchone()["cnt"]

    def get_violation_count(self, user_id: str, group_id: str) -> int:
        """获取用户在该群的违规次数"""
        c = self.conn.cursor()
        c.execute(
            "SELECT COUNT(*) as cnt FROM violations WHERE user_id = ? AND group_id = ?",
            (user_id, group_id),
        )
        return c.fetchone()["cnt"]

    def close(self):
        self.conn.close()

    def _today(self) -> str:
        return datetime.now().strftime("%Y-%m-%d")

    def cleanup_old_records(self, retention_days: int) -> int:
        if retention_days <= 0:
            return 0
        cutoff = (datetime.now() - timedelta(days=retention_days)).strftime("%Y-%m-%d %H:%M:%S")
        c = self.conn.cursor()
        c.execute("DELETE FROM checks WHERE created_at < ?", (cutoff,))
        deleted = c.rowcount
        self.conn.commit()
        return deleted

    def get_user(self, user_id: str) -> Optional[sqlite3.Row]:
        c = self.conn.cursor()
        c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        return c.fetchone()

    def get_or_create_user(self, user_id: str, user_name: str = "") -> sqlite3.Row:
        user = self.get_user(user_id)
        if not user:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            c = self.conn.cursor()
            c.execute(
                "INSERT INTO users (user_id, user_name, avg_score, total_checks, daily_count, last_check_date, created_at, updated_at) VALUES (?, ?, 0, 0, 0, ?, ?, ?)",
                (user_id, user_name, self._today(), now, now),
            )
            self.conn.commit()
            c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            user = c.fetchone()
        elif user_name and not user["user_name"]:
            c = self.conn.cursor()
            c.execute("UPDATE users SET user_name = ? WHERE user_id = ?", (user_name, user_id))
            self.conn.commit()
            c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            user = c.fetchone()
        return user

    def check_daily_limit(self, user_id: str, daily_limit: int) -> Tuple[bool, int]:
        if daily_limit <= 0:
            return True, -1
        user = self.get_or_create_user(user_id)
        today = self._today()
        if user["last_check_date"] != today:
            c = self.conn.cursor()
            c.execute(
                "UPDATE users SET daily_count = 0, last_check_date = ? WHERE user_id = ?",
                (today, user_id),
            )
            self.conn.commit()
            return True, daily_limit
        remaining = daily_limit - user["daily_count"]
        return remaining > 0, max(0, remaining)

    def record_check(
        self,
        user_id: str,
        user_name: str,
        score: float,
        level: str,
        reason: str,
        message_preview: str,
        source_group: str,
        store_history: bool,
    ) -> Dict[str, Any]:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        user = self.get_or_create_user(user_id, user_name)
        total_checks = user["total_checks"] + 1
        old_avg = user["avg_score"]
        new_avg = round((old_avg * (total_checks - 1) + score) / total_checks, 2)

        c = self.conn.cursor()
        c.execute(
            "UPDATE users SET user_name = ?, avg_score = ?, total_checks = ?, daily_count = daily_count + 1, last_check_date = ?, updated_at = ? WHERE user_id = ?",
            (user_name, new_avg, total_checks, self._today(), now, user_id),
        )
        if store_history:
            preview = message_preview[:200] if message_preview else ""
            c.execute(
                "INSERT INTO checks (user_id, score, level, reason, message_preview, source_group, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (user_id, score, level, reason[:300] if reason else "", preview, source_group, now),
            )
        self.conn.commit()
        return {"avg_score": new_avg, "total_checks": total_checks, "created_at": now}

    def get_ranking(self, limit: int) -> List[sqlite3.Row]:
        c = self.conn.cursor()
        c.execute(
            "SELECT user_id, user_name, avg_score, total_checks FROM users WHERE total_checks > 0 ORDER BY avg_score DESC LIMIT ?",
            (limit,),
        )
        return c.fetchall()

    def get_all_users(self) -> List[sqlite3.Row]:
        c = self.conn.cursor()
        c.execute(
            "SELECT user_id, user_name, avg_score, total_checks, created_at, updated_at FROM users WHERE total_checks > 0 ORDER BY avg_score DESC"
        )
        return c.fetchall()

    def get_user_records(self, user_id: str) -> List[sqlite3.Row]:
        c = self.conn.cursor()
        c.execute(
            "SELECT * FROM checks WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        )
        return c.fetchall()

    def update_record_score(self, record_id: int, new_score: float, level: str) -> bool:
        c = self.conn.cursor()
        c.execute(
            "UPDATE checks SET score = ?, level = ? WHERE id = ?",
            (new_score, level, record_id),
        )
        if c.rowcount > 0:
            self.conn.commit()
            # 重新计算该用户平均分
            c.execute("SELECT user_id FROM checks WHERE id = ?", (record_id,))
            row = c.fetchone()
            if row:
                self._recalculate_user_avg_by_id(row["user_id"])
            return True
        return False

    def delete_record(self, record_id: int) -> bool:
        c = self.conn.cursor()
        c.execute("SELECT user_id FROM checks WHERE id = ?", (record_id,))
        row = c.fetchone()
        if not row:
            return False
        user_id = row["user_id"]
        c.execute("DELETE FROM checks WHERE id = ?", (record_id,))
        if c.rowcount > 0:
            self.conn.commit()
            self._recalculate_user_avg_by_id(user_id)
            return True
        return False

    def _recalculate_user_avg_by_id(self, user_id: str):
        c = self.conn.cursor()
        c.execute(
            "SELECT COUNT(*) as cnt, AVG(score) as avg_val FROM checks WHERE user_id = ?",
            (user_id,),
        )
        row = c.fetchone()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if row and row["cnt"] > 0:
            c.execute(
                "UPDATE users SET avg_score = ?, total_checks = ?, updated_at = ? WHERE user_id = ?",
                (round(row["avg_val"], 2), row["cnt"], now, user_id),
            )
        else:
            c.execute(
                "UPDATE users SET avg_score = 0, total_checks = 0, updated_at = ? WHERE user_id = ?",
                (now, user_id),
            )
        self.conn.commit()

    def reset_user(self, user_id: str) -> bool:
        c = self.conn.cursor()
        user = self.get_user(user_id)
        if not user:
            return False
        c.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
        c.execute("DELETE FROM checks WHERE user_id = ?", (user_id,))
        self.conn.commit()
        return True

    def get_stats(self) -> Dict[str, Any]:
        c = self.conn.cursor()
        c.execute("SELECT COUNT(*) as cnt FROM users WHERE total_checks > 0")
        total_users = c.fetchone()["cnt"]
        c.execute("SELECT SUM(total_checks) as cnt FROM users")
        total_checks = c.fetchone()["cnt"] or 0
        c.execute("SELECT AVG(avg_score) as avg_val FROM users WHERE total_checks > 0")
        overall_avg = c.fetchone()["avg_val"]
        return {
            "total_users": total_users,
            "total_checks": total_checks,
            "overall_avg": round(overall_avg, 2) if overall_avg else 0,
        }


# ========== 评分等级系统 ==========
class LevelSystem:
    def __init__(self, config: AstrBotConfig):
        self.config = config

    def get_level(self, score: float) -> Tuple[str, str]:
        score = max(0, min(100, score))
        thresholds = {
            "credible": self.config.get("threshold_credible", 80),
            "reliable": self.config.get("threshold_reliable", 60),
            "doubtful": self.config.get("threshold_doubtful", 40),
            "suspicious": self.config.get("threshold_suspicious", 20),
            "false": self.config.get("threshold_false", 0),
        }
        level_names = {
            "credible": self.config.get("level_name_credible", "可信"),
            "reliable": self.config.get("level_name_reliable", "基本可信"),
            "doubtful": self.config.get("level_name_doubtful", "存疑"),
            "suspicious": self.config.get("level_name_suspicious", "可疑"),
            "false": self.config.get("level_name_false", "虚假"),
        }
        for key in ["credible", "reliable", "doubtful", "suspicious", "false"]:
            if score >= thresholds[key]:
                return key, level_names[key]
        return "false", level_names["false"]

    def get_icon(self, level_key: str) -> str:
        if not self.config.get("show_icon", True):
            return ""
        return ICON_MAP.get(level_key, "")


# ========== 规则引擎（增强版）==========
class RuleEngine:
    def __init__(self, config: AstrBotConfig):
        self.config = config

    def analyze(self, text: str) -> Tuple[float, str]:
        if not text or len(text.strip()) == 0:
            return 0, "空消息，无法分析"

        score = float(self.config.get("rule_base_score", 50))
        reasons = []
        text_stripped = text.strip()
        length = len(text_stripped)

        # === 1. 细节丰富度分析 ===
        detail_count = 0
        # 数字细节
        numbers = re.findall(r"\d+\.?\d*", text)
        detail_count += len(numbers)
        # 时间词
        time_words = ["今天", "昨天", "前天", "明天", "后天", "上周", "下周",
                      "上个月", "下个月", "去年", "明年", "刚才", "之前", "以后",
                      "早上", "中午", "晚上", "凌晨", "半夜"]
        for w in time_words:
            if w in text:
                detail_count += 1
        # 地点词
        location_chars = ["京", "沪", "广", "深", "省", "市", "县", "区", "镇",
                          "路", "街", "号", "楼", "层", "室", "村", "乡"]
        for c in location_chars:
            if c in text:
                detail_count += 1
                break
        # 人名/称呼
        name_patterns = re.findall(r"(?:老|小|阿)[\u4e00-\u9fff]{1,3}|[\u4e00-\u9fff]{2,4}(?:老师|先生|女士|姐|哥|叔|姨|婆)", text)
        detail_count += len(name_patterns)
        # 具体量词
        measure_words = re.findall(r"[\u4e00-\u9fff]+(?:个|只|条|件|次|遍|趟|顿|杯|碗|块|片|张|把|棵|辆|架|艘)", text)
        detail_count += min(len(measure_words), 3)

        if detail_count >= 5:
            bonus = 20
            score += bonus
            reasons.append(f"细节非常丰富(+{bonus})")
        elif detail_count >= 3:
            bonus = 12
            score += bonus
            reasons.append(f"细节较丰富(+{bonus})")
        elif detail_count >= 1:
            bonus = 6
            score += bonus
            reasons.append(f"有一些细节(+{bonus})")
        else:
            penalty = 5
            score -= penalty
            reasons.append(f"缺乏具体细节(-{penalty})")

        # === 2. 长度评分 ===
        opt_min = self.config.get("rule_length_optimal_min", 10)
        opt_max = self.config.get("rule_length_optimal_max", 80)
        if opt_min <= length <= opt_max:
            bonus = self.config.get("rule_length_optimal_bonus", 15)
            score += bonus
            reasons.append(f"长度适中(+{bonus})")
        elif length < opt_min:
            penalty = min(opt_min - length, 15)
            score -= penalty
            reasons.append(f"内容过短(-{penalty})")
        elif length > opt_max * 2:
            penalty = 15
            score -= penalty
            reasons.append(f"过于冗长(-{penalty})")
        else:
            penalty = min((length - opt_max) // 10, 10)
            score -= penalty
            reasons.append(f"略长(-{penalty})")

        # === 3. 反常识/夸张词 ===
        absurd_cnt = sum(1 for w in ABSURD_WORDS if w in text)
        if absurd_cnt > 0:
            penalty = absurd_cnt * self.config.get("rule_absurd_penalty", 20)
            score -= penalty
            reasons.append(f"夸张/反常识表述(-{penalty})")

        # === 4. 绝对化表述（结合常识判断）===
        abs_cnt = sum(1 for w in ABSOLUTE_WORDS if w in text)
        # 检查是否包含常识性内容
        common_sense_cnt = sum(1 for w in COMMON_SENSE_WORDS if w in text)
        is_common_sense = common_sense_cnt >= 2  # 包含2个以上常识词视为常识性陈述

        if abs_cnt >= 3:
            if is_common_sense:
                # 常识性内容中的绝对化表述，惩罚减轻
                penalty = 10
                score -= penalty
                reasons.append(f"绝对化表述但属常识(-{penalty})")
            else:
                penalty = 25
                score -= penalty
                reasons.append(f"大量绝对化表述(-{penalty})")
        elif abs_cnt > 0:
            if is_common_sense:
                # 常识性内容中的绝对化表述，不惩罚或轻微惩罚
                penalty = 0
                reasons.append("绝对化表述但属常识(不扣分)")
            else:
                penalty = abs_cnt * self.config.get("rule_absolute_penalty", 10)
                score -= penalty
                reasons.append(f"绝对化表述(-{penalty})")

        # === 5. 模糊表述 ===
        vague_cnt = sum(1 for w in VAGUE_WORDS if w in text)
        if vague_cnt >= 3:
            penalty = 20
            score -= penalty
            reasons.append(f"大量模糊表述(-{penalty})")
        elif vague_cnt > 0:
            penalty = vague_cnt * self.config.get("rule_vague_penalty", 8)
            score -= penalty
            reasons.append(f"模糊表述(-{penalty})")

        # === 6. 情感化语言 ===
        emotion_cnt = sum(1 for w in EMOTION_WORDS if w in text)
        if emotion_cnt >= 2:
            penalty = 15
            score -= penalty
            reasons.append(f"情绪化语言(-{penalty})")
        elif emotion_cnt > 0:
            penalty = 8
            score -= penalty
            reasons.append(f"带有情绪(-{penalty})")

        # === 7. 情感符号 ===
        emotion_chars = re.findall(r"[!！?？]{2,}", text)
        if len(emotion_chars) >= 2:
            penalty = 8
            score -= penalty
            reasons.append(f"过多感叹/问号(-{penalty})")
        elif len(emotion_chars) == 1:
            bonus = 3
            score += bonus
            reasons.append(f"适度情感表达(+{bonus})")

        # === 8. 第一人称亲历叙述（加分）===
        first_person_cnt = sum(1 for w in FIRST_PERSON_WORDS if w in text)
        if first_person_cnt > 0:
            bonus = first_person_cnt * 5
            score += bonus
            reasons.append(f"第一人称亲历叙述(+{bonus})")

        # === 9. 转折/客观表述（加分）===
        contradict_cnt = sum(1 for w in CONTRADICT_WORDS if w in text)
        if contradict_cnt > 0:
            bonus = contradict_cnt * 4
            score += bonus
            reasons.append(f"有转折/客观表述(+{bonus})")

        # === 10. 句式多样性 ===
        sentences = re.split(r"[。！？!?\n]", text)
        sentences = [s for s in sentences if s.strip()]
        if len(sentences) >= 3:
            bonus = 8
            score += bonus
            reasons.append(f"多句式表述(+{bonus})")
        elif len(sentences) == 2:
            bonus = 3
            score += bonus
            reasons.append(f"双句式表述(+{bonus})")

        # === 11. 重复/啰嗦检测 ===
        if length > 20:
            # 检测重复片段
            repeated = False
            for seg_len in range(4, min(length // 2, 15)):
                for i in range(length - seg_len * 2 + 1):
                    seg = text_stripped[i:i + seg_len]
                    if text_stripped.count(seg) >= 3:
                        repeated = True
                        break
                if repeated:
                    break
            if repeated:
                penalty = 10
                score -= penalty
                reasons.append(f"存在重复内容(-{penalty})")

        # === 12. 表情/emoji 使用 ===
        emoji_pattern = re.compile(r"[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF\u2600-\u26FF\u2700-\u27BF]")
        emojis = emoji_pattern.findall(text)
        if len(emojis) >= 3:
            penalty = 5
            score -= penalty
            reasons.append(f"大量表情符号(-{penalty})")

        score = max(0.0, min(100.0, score))
        reason_str = "；".join(reasons) if reasons else "无明显特征"
        return round(score, 1), reason_str


# ========== LLM 引擎 ==========
class LLMEngine:
    def __init__(self, config: AstrBotConfig, context: Context):
        self.config = config
        self.context = context

    async def analyze(self, text: str, umo: str = None) -> Optional[Tuple[float, str]]:
        if not self.config.get("enable_llm", True):
            return None
        if not text or len(text.strip()) == 0:
            return 0, "空消息，无法分析"

        prompt_template = self.config.get("prompt_template", DEFAULT_PROMPT)
        prompt = prompt_template.replace("{message}", text)

        response_text = await self._call_llm(prompt, umo)
        if response_text is None:
            return None
        return self._parse_response(response_text)

    async def _call_llm(self, prompt: str, umo: str = None) -> Optional[str]:
        """通过 AstrBot 原生接口调用 LLM"""
        provider_id = self.config.get("llm_provider_id", "")

        # 方式1：使用新接口 llm_generate + 指定 provider
        if provider_id:
            try:
                llm_resp = await self.context.llm_generate(
                    chat_provider_id=provider_id,
                    prompt=prompt,
                )
                if llm_resp and llm_resp.completion_text:
                    return llm_resp.completion_text
            except Exception as e:
                logger.warning(f"[查证器] llm_generate 指定Provider失败: {e}")

        # 方式2：使用当前会话 provider + llm_generate
        if umo:
            try:
                pid = await self.context.get_current_chat_provider_id(umo=umo)
                if pid:
                    llm_resp = await self.context.llm_generate(
                        chat_provider_id=pid,
                        prompt=prompt,
                    )
                    if llm_resp and llm_resp.completion_text:
                        return llm_resp.completion_text
            except Exception as e:
                logger.warning(f"[查证器] llm_generate 会话Provider失败: {e}")

        # 方式3：回退到旧接口 get_using_provider
        try:
            provider = None
            if umo:
                try:
                    provider = self.context.get_using_provider(umo=umo)
                except Exception:
                    pass
            if not provider:
                try:
                    provider = self.context.get_using_provider()
                except Exception:
                    pass
            if provider:
                llm_resp = await provider.text_chat(
                    prompt=prompt,
                    session_id="lie_detector",
                    context=[],
                    system_prompt="",
                )
                if llm_resp and llm_resp.completion_text:
                    return llm_resp.completion_text
        except Exception as e:
            logger.error(f"[查证器] Provider回退调用失败: {e}")

        return None

    def _parse_response(self, response: str) -> Optional[Tuple[float, str]]:
        if not response:
            return None
        try:
            # 支持整数和小数评分
            score_match = re.search(r"评分[：:]\s*(\d+\.?\d*)", response)
            reason_match = re.search(r"理由[：:]\s*(.+)", response)
            score = None
            reason = ""
            if score_match:
                try:
                    score = max(0, min(100, float(score_match.group(1))))
                except ValueError:
                    pass
            if reason_match:
                reason = reason_match.group(1).strip()
            if score is not None:
                return round(score, 1), reason or "LLM分析完成"
            return None
        except Exception as e:
            logger.error(f"[查证器] LLM响应解析失败: {e}")
            return None


# ========== 消息格式化 ==========
class MessageFormatter:
    def __init__(self, config: AstrBotConfig, level_system: LevelSystem):
        self.config = config
        self.level_system = level_system

    def format_result(
        self,
        score: float,
        reason: str,
        target_user_name: str,
        user_stats: Optional[Dict[str, Any]] = None,
    ) -> str:
        level_key, level_name = self.level_system.get_level(score)
        icon = self.level_system.get_icon(level_key)

        lines = [f"📊 查证报告" + (f" —— {target_user_name}" if target_user_name else "")]
        lines.append("─" * 20)

        score_line = f"可信度: {int(round(score))}%"
        lines.append(f"{icon} {score_line}" if icon else score_line)
        verdict = f"判定等级: {level_name}"
        lines.append(f"{icon} {verdict}" if icon else verdict)

        if self.config.get("show_reason", True) and reason:
            lines.append(f"分析理由: {reason}")

        if self.config.get("show_history_avg", True) and user_stats:
            lines.append("─" * 20)
            lines.append(f"累计查证: {user_stats['total_checks']} 次")
            lines.append(f"历史均分: {int(round(user_stats['avg_score']))}%")

        return "\n".join(lines)

    def format_personal_stats(self, user_name: str, user_row: sqlite3.Row) -> str:
        level_key, level_name = self.level_system.get_level(user_row["avg_score"])
        icon = self.level_system.get_icon(level_key)
        display_name = user_row["user_name"] or user_name
        lines = [f"📊 个人查证统计 —— {display_name}", "─" * 20]
        avg_line = f"平均可信度: {int(round(user_row['avg_score']))}%"
        lines.append(f"{icon} {avg_line}" if icon else avg_line)
        lines.append(f"累计等级: {level_name}")
        lines.append(f"查证次数: {user_row['total_checks']} 次")
        return "\n".join(lines)

    def format_ranking(self, rows: List[sqlite3.Row], limit: int) -> str:
        lines = [f"🏆 可信度排行榜 (Top {min(limit, len(rows))})", "─" * 20]
        if not rows:
            lines.append("暂无查证记录。")
            return "\n".join(lines)
        medals = ["🥇", "🥈", "🥉"]
        for idx, row in enumerate(rows):
            rank = idx + 1
            medal = medals[idx] if idx < len(medals) else f"  {rank}. "
            user_display = row["user_id"]
            level_key, _ = self.level_system.get_level(row["avg_score"])
            icon = self.level_system.get_icon(level_key)
            lines.append(f"{medal} {user_display} {icon} {int(round(row['avg_score']))}% ({row['total_checks']}次)")
        return "\n".join(lines)


# ========== 插件主类 ==========
@register(PLUGIN_NAME, "AstrBot Community", "查证器插件 - 分析消息可信度，支持LLM和规则双引擎，带WebUI管理面板", "3.0.0", "")
class LieDetectorPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.db = DatabaseManager()
        self.level_system = LevelSystem(config)
        self.rule_engine = RuleEngine(config)
        self.llm_engine = LLMEngine(config, context)
        self.formatter = MessageFormatter(config, self.level_system)

        # 启动时清理旧记录
        retention = config.get("history_retention_days", 30)
        if retention > 0 and config.get("store_history", True):
            deleted = self.db.cleanup_old_records(retention)
            if deleted > 0:
                logger.info(f"[查证器] 清理过期历史记录: {deleted} 条")

        # 注册 WebUI 后端 API
        self._register_web_apis()

    def _register_web_apis(self):
        """注册 WebUI 面板后端 API（路径必须包含插件名前缀）"""
        routes = [
            (f"/{PLUGIN_NAME}/stats", self.api_get_stats, ["GET"], "获取总览统计"),
            (f"/{PLUGIN_NAME}/users", self.api_get_users, ["GET"], "获取所有用户列表"),
            (f"/{PLUGIN_NAME}/records", self.api_get_records, ["GET"], "获取用户查证记录"),
            (f"/{PLUGIN_NAME}/records/update", self.api_update_record, ["POST"], "更新查证记录"),
            (f"/{PLUGIN_NAME}/records/delete", self.api_delete_record, ["POST"], "删除查证记录"),
            (f"/{PLUGIN_NAME}/users/reset", self.api_reset_user, ["POST"], "重置用户数据"),
        ]
        for path, handler, methods, desc in routes:
            try:
                self.context.register_web_api(path, handler, methods, desc)
            except Exception as e:
                logger.error(f"[查证器] 注册API失败 {path}: {e}")

    # ========== WebUI API 处理 ==========

    async def api_get_stats(self):
        try:
            stats = self.db.get_stats()
            return json_response(stats)
        except Exception as e:
            logger.error(f"[查证器] 获取统计失败: {e}")
            return error_response(f"获取统计失败: {e}")

    async def api_get_users(self):
        try:
            rows = self.db.get_all_users()
            users = []
            for row in rows:
                level_key, level_name = self.level_system.get_level(row["avg_score"])
                icon = self.level_system.get_icon(level_key)
                users.append({
                    "user_id": row["user_id"],
                    "user_name": row["user_name"] or row["user_id"],
                    "avg_score": round(row["avg_score"], 1),
                    "total_checks": row["total_checks"],
                    "level": level_name,
                    "icon": icon,
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                })
            return json_response(users)
        except Exception as e:
            logger.error(f"[查证器] 获取用户列表失败: {e}")
            return error_response(f"获取用户列表失败: {e}")

    async def api_get_records(self):
        try:
            user_id = request.query.get("user_id", "")
            if not user_id:
                return error_response("缺少 user_id 参数")
            rows = self.db.get_user_records(user_id)
            records = []
            for row in rows:
                level_key, level_name = self.level_system.get_level(row["score"])
                icon = self.level_system.get_icon(level_key)
                # 获取来源群信息，如果为空则显示"私聊"
                source_group = row["source_group"] if row["source_group"] else "私聊"
                records.append({
                    "id": row["id"],
                    "user_id": row["user_id"],
                    "user_name": row["user_id"],  # 本地数据库没有 user_name 字段
                    "score": round(row["score"], 1),
                    "level": level_name,
                    "icon": icon,
                    "reason": row["reason"],
                    "message_preview": row["message_preview"],
                    "source_group": source_group,
                    "created_at": row["created_at"],
                })
            return json_response(records)
        except Exception as e:
            logger.error(f"[查证器] 获取记录失败: {e}")
            return error_response(f"获取记录失败: {e}")

    async def api_update_record(self):
        try:
            data = await request.get_json()
            record_id = data.get("record_id")
            new_score = data.get("score")
            if record_id is None or new_score is None:
                return error_response("缺少 record_id 或 score")
            new_score = max(0, min(100, float(new_score)))
            level_key, _ = self.level_system.get_level(new_score)
            success = self.db.update_record_score(int(record_id), new_score, level_key)
            if success:
                return json_response({"message": "记录已更新"})
            return error_response("记录不存在或更新失败")
        except Exception as e:
            logger.error(f"[查证器] 更新记录失败: {e}")
            return error_response(f"更新记录失败: {e}")

    async def api_delete_record(self):
        try:
            data = await request.get_json()
            record_id = data.get("record_id")
            if record_id is None:
                return error_response("缺少 record_id")
            success = self.db.delete_record(int(record_id))
            if success:
                return json_response({"message": "记录已删除"})
            return error_response("记录不存在")
        except Exception as e:
            logger.error(f"[查证器] 删除记录失败: {e}")
            return error_response(f"删除记录失败: {e}")

    async def api_reset_user(self):
        try:
            data = await request.get_json()
            user_id = data.get("user_id")
            if not user_id:
                return error_response("缺少 user_id")
            success = self.db.reset_user(user_id)
            if success:
                return json_response({"message": "用户数据已清除"})
            return error_response("用户不存在或无数据")
        except Exception as e:
            logger.error(f"[查证器] 重置失败: {e}")
            return error_response(f"重置失败: {e}")

    # ========== 命令处理 ==========

    async def _handle_command(self, event: AstrMessageEvent, cmd_prefix: str):
        """统一处理 /查证 和 /测谎 命令"""
        try:
            # 提取参数
            raw_text = event.message_str.strip()
            args = raw_text
            for prefix in [cmd_prefix, f"/{cmd_prefix}"]:
                if args.startswith(prefix):
                    args = args[len(prefix):].strip()
                    break

            subcmd = args.split(maxsplit=1)[0].lower() if args else ""

            # --- 子命令: 统计 ---
            if subcmd in ["统计", "排行榜", "rank", "ranking"]:
                sub_args = args[len(subcmd):].strip() if args else ""
                if sub_args:
                    target_id = self._extract_at_target(event)
                    if not target_id:
                        target_id = sub_args.strip().lstrip("@").strip()
                    if target_id:
                        user = self.db.get_user(target_id)
                        if not user or user["total_checks"] == 0:
                            yield event.plain_result(f"用户 {target_id} 暂无查证记录。")
                            return
                        yield event.plain_result(
                            self.formatter.format_personal_stats(target_id, user)
                        )
                        return
                    yield event.plain_result("未找到目标用户。请使用 @用户 或指定用户ID。")
                    return
                limit = self.config.get("ranking_limit", 20)
                rows = self.db.get_ranking(limit)
                yield event.plain_result(self.formatter.format_ranking(rows, limit))
                return

            # --- 子命令: 重置 ---
            if subcmd in ["重置", "清除", "reset", "clear"]:
                is_admin = await self._is_admin(event)
                if not is_admin:
                    yield event.plain_result("❌ 只有管理员可以使用重置功能。")
                    return
                target_id = self._extract_at_target(event)
                if not target_id:
                    sub_args = args[len(subcmd):].strip() if args else ""
                    target_id = sub_args.lstrip("@").strip()
                if not target_id:
                    yield event.plain_result(f"请指定要重置的用户：/{cmd_prefix} 重置 @用户")
                    return
                success = self.db.reset_user(target_id)
                if success:
                    yield event.plain_result(f"✅ 已清除用户 {target_id} 的所有查证数据。")
                else:
                    yield event.plain_result(f"用户 {target_id} 不存在或无数据。")
                return

            # --- 子命令: 帮助 ---
            if subcmd in ["帮助", "help", "用法", "?"]:
                yield event.plain_result(self._get_help_text())
                return

            # --- 主功能: 查证 ---
            if self.config.get("admin_only", False):
                is_admin = await self._is_admin(event)
                if not is_admin:
                    yield event.plain_result("❌ 当前插件仅管理员可用。")
                    return

            # 获取引用消息
            quoted_text, quoted_user_id, quoted_user_name = self._get_quoted_message(event)
            if not quoted_text:
                yield event.plain_result(
                    f"❌ 请引用（回复）一条消息后再使用 /{cmd_prefix} 命令。\n"
                    f"用法：回复某条消息 → 输入 /{cmd_prefix}"
                )
                return

            min_len = self.config.get("min_message_length", 2)
            if len(quoted_text.strip()) < min_len:
                yield event.plain_result(f"❌ 被查证的消息过短（至少 {min_len} 字）。")
                return

            # 每日限制（限制操作者）
            operator_id = event.get_sender_id()
            daily_limit = self.config.get("daily_limit_per_user", 0)
            can_use, remaining = self.db.check_daily_limit(operator_id, daily_limit)
            if not can_use:
                yield event.plain_result(f"❌ 您今日的查证次数已用完（上限 {daily_limit} 次）。")
                return

            # 分析
            score = None
            reason = ""
            umo = event.unified_msg_origin

            if self.config.get("enable_llm", True):
                llm_result = await self.llm_engine.analyze(quoted_text, umo)
                if llm_result is not None:
                    score, reason = llm_result

            if score is None:
                score, reason = self.rule_engine.analyze(quoted_text)

            # 记录到被引用消息的作者（而非操作者）
            record_uid = quoted_user_id if quoted_user_id else operator_id
            record_uname = quoted_user_name or ""
            
            # 检测违规内容（分数为0且理由包含不当内容关键词）
            is_violation = score == 0 and any(kw in reason for kw in ["涉黄", "色情", "不当", "侮辱", "攻击", "歧视"])
            
            if is_violation:
                # 获取群ID
                group_id = self._extract_group_id(event)
                if group_id:
                    # 记录违规
                    violation_count = self.db.add_violation(
                        user_id=record_uid,
                        group_id=group_id,
                        violation_type="不当内容",
                        message_content=quoted_text
                    )
                    
                    # 检查是否有管理员权限
                    is_admin = await self._is_admin(event)
                    
                    if violation_count == 1:
                        # 第1次违规
                        if is_admin:
                            yield event.plain_result("⚠️ 禁止发送违规内容，再触犯一次将会被禁言，再触犯两次将会被给予飞机票")
                        else:
                            yield event.plain_result("⚠️ 禁止发送违规内容")
                    elif violation_count == 2:
                        # 第2次违规：禁言
                        if is_admin:
                            # 尝试禁言
                            await self._mute_user(event, record_uid, group_id)
                            yield event.plain_result(f"⚠️ 用户 {record_uid} 因多次违规已被禁言")
                        else:
                            yield event.plain_result("⚠️ 禁止发送违规内容")
                    else:
                        # 第3次及以上违规：踢出
                        if is_admin:
                            # 尝试踢出
                            await self._kick_user(event, record_uid, group_id)
                            yield event.plain_result(f"✈️ 用户 {record_uid} 因多次违规已被移出群聊")
                        else:
                            yield event.plain_result("⚠️ 禁止发送违规内容")
                    
                    # 向警报群发送通知
                    await self._send_violation_alert(event, record_uid, group_id, quoted_text, violation_count)
                    return

            # 获取来源群信息
            source_group = self._get_source_group(event)
            store_history = self.config.get("store_history", True)
            stats = self.db.record_check(
                user_id=record_uid,
                user_name=record_uname,
                score=score,
                level=self.level_system.get_level(score)[0],
                reason=reason,
                message_preview=quoted_text,
                source_group=source_group,
                store_history=store_history,
            )

            display_stats = stats if quoted_user_id else None
            target_display = quoted_user_name or (quoted_user_id if quoted_user_id else "")
            result_msg = self.formatter.format_result(
                score=score, reason=reason,
                target_user_name=target_display, user_stats=display_stats,
            )
            if daily_limit > 0 and remaining > 0:
                result_msg += f"\n\n💡 今日剩余查证次数: {remaining - 1}/{daily_limit}"

            yield event.plain_result(result_msg)

        except Exception as e:
            logger.error(f"[查证器] 处理命令出错: {e}")
            import traceback
            traceback.print_exc()
            yield event.plain_result(f"❌ 查证插件内部错误: {e}")

    @filter.command("查证")
    async def handle_lie_detector(self, event: AstrMessageEvent):
        """处理 /查证 命令"""
        async for result in self._handle_command(event, "查证"):
            yield result

    @filter.command("测谎")
    async def handle_lie_detector_alias(self, event: AstrMessageEvent):
        """处理 /测谎 命令（别名）"""
        async for result in self._handle_command(event, "测谎"):
            yield result

    # ========== 辅助方法 ==========

    def _extract_group_id(self, event: AstrMessageEvent) -> Optional[str]:
        """从事件中提取群ID"""
        try:
            # 尝试从 unified_msg_origin 提取
            if hasattr(event, "unified_msg_origin") and event.unified_msg_origin:
                origin = str(event.unified_msg_origin)
                parts = origin.split(":")
                if len(parts) >= 3 and "group" in parts[1].lower():
                    return parts[2]
            
            # 尝试从 message_obj 获取
            if hasattr(event, "message_obj") and event.message_obj:
                msg_obj = event.message_obj
                if hasattr(msg_obj, "group_id") and msg_obj.group_id:
                    return str(msg_obj.group_id)
                if hasattr(msg_obj, "session_id"):
                    return str(msg_obj.session_id)
            
            return None
        except Exception as e:
            logger.error(f"[查证器] 提取群ID失败: {e}")
            return None

    async def _mute_user(self, event: AstrMessageEvent, user_id: str, group_id: str):
        """禁言用户"""
        try:
            # 使用 AstrBot 的 API 禁言用户
            if hasattr(event, "send") and hasattr(event.send, "mute"):
                await event.send.mute(group_id, user_id, duration=3600)  # 禁言1小时
            logger.info(f"[查证器] 已禁言用户 {user_id} 在群 {group_id}")
        except Exception as e:
            logger.error(f"[查证器] 禁言用户失败: {e}")

    async def _kick_user(self, event: AstrMessageEvent, user_id: str, group_id: str):
        """踢出用户"""
        try:
            # 使用 AstrBot 的 API 踢出用户
            if hasattr(event, "send") and hasattr(event.send, "kick"):
                await event.send.kick(group_id, user_id)
            logger.info(f"[查证器] 已踢出用户 {user_id} 从群 {group_id}")
        except Exception as e:
            logger.error(f"[查证器] 踢出用户失败: {e}")

    async def _send_violation_alert(self, event: AstrMessageEvent, user_id: str, group_id: str, message: str, violation_count: int):
        """向警报群发送违规通知"""
        try:
            alert_group = self.config.get("violation_alert_group", "")
            if not alert_group:
                return
            
            # 构建警报消息
            alert_msg = (
                f"🚨 违规内容警报\n"
                f"用户: {user_id}\n"
                f"来源群: {group_id}\n"
                f"违规次数: {violation_count}\n"
                f"违规内容: {message[:100]}"
            )
            
            # 发送到警报群
            if hasattr(event, "send") and hasattr(event.send, "send_group_msg"):
                await event.send.send_group_group(alert_group, alert_msg)
            logger.info(f"[查证器] 已向警报群 {alert_group} 发送违规通知")
        except Exception as e:
            logger.error(f"[查证器] 发送违规警报失败: {e}")

    async def _is_admin(self, event: AstrMessageEvent) -> bool:
        try:
            if hasattr(event, "is_admin") and event.is_admin:
                return True
            if hasattr(event, "role"):
                return event.role in ["admin", "owner", "administrator"]
            return False
        except Exception:
            return False

    def _get_quoted_message(self, event: AstrMessageEvent) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """获取被引用消息 (text, user_id, user_name)"""
        try:
            msg_obj = event.message_obj
            if msg_obj and hasattr(msg_obj, "reply") and msg_obj.reply:
                reply = msg_obj.reply
                text = getattr(reply, "message_str", None) or ""
                if not text and hasattr(reply, "message") and reply.message:
                    text = self._extract_chain_text(reply.message)
                uid = getattr(reply, "sender_id", None) or getattr(reply, "user_id", None)
                uname = getattr(reply, "sender_name", None) or getattr(reply, "nickname", None)
                if text:
                    return text.strip(), str(uid) if uid else None, uname

            # 检查消息链中的 Reply 组件
            if msg_obj and hasattr(msg_obj, "message") and msg_obj.message:
                for comp in msg_obj.message:
                    comp_name = type(comp).__name__
                    if "Reply" in comp_name or "reply" in comp_name.lower():
                        text = getattr(comp, "message_str", None) or ""
                        if not text and hasattr(comp, "chain") and comp.chain:
                            text = self._extract_chain_text(comp.chain)
                        uid = getattr(comp, "user_id", None) or getattr(comp, "sender_id", None)
                        uname = getattr(comp, "sender_name", None) or getattr(comp, "nickname", None)
                        if text:
                            return text.strip(), str(uid) if uid else None, uname
        except Exception as e:
            logger.error(f"[查证器] 获取引用消息失败: {e}")
        return None, None, None

    def _extract_chain_text(self, message) -> str:
        if message is None:
            return ""
        if isinstance(message, str):
            return message.strip()
        parts = []
        if isinstance(message, (list, tuple)):
            for seg in message:
                if hasattr(seg, "text") and seg.text:
                    parts.append(str(seg.text))
                elif isinstance(seg, str):
                    parts.append(seg)
        else:
            if hasattr(message, "text") and message.text:
                parts.append(str(message.text))
        return "".join(parts).strip()

    def _extract_at_target(self, event: AstrMessageEvent) -> Optional[str]:
        """从消息链中提取 @ 目标的 user_id"""
        try:
            msg_obj = event.message_obj
            if msg_obj and hasattr(msg_obj, "message") and msg_obj.message:
                for comp in msg_obj.message:
                    comp_name = type(comp).__name__
                    if "At" in comp_name or "Mention" in comp_name:
                        uid = getattr(comp, "qq", None) or getattr(comp, "user_id", None) or getattr(comp, "target", None)
                        if uid:
                            return str(uid)
        except Exception:
            pass
        return None

    def _get_source_group(self, event: AstrMessageEvent) -> str:
        """获取消息来源群信息"""
        try:
            # 调试日志：输出原始信息
            umo = getattr(event, "unified_msg_origin", None)
            msg_obj = getattr(event, "message_obj", None)
            logger.debug(f"[查证器] UMO: {umo}, message_obj type: {type(msg_obj)}")
            
            # 尝试从 unified_msg_origin 提取群信息
            if umo:
                origin = str(umo)
                parts = origin.split(":")
                
                # 格式1: platform_id:message_type:session_id
                if len(parts) >= 3:
                    msg_type = parts[1].lower()
                    session_id = parts[2]
                    if "group" in msg_type:
                        return f"群:{session_id}"
                    elif "friend" in msg_type or "private" in msg_type:
                        return "私聊"
                    else:
                        return f"{msg_type}:{session_id}"
                
                # 格式2: platform_id:session_id (旧格式)
                elif len(parts) == 2:
                    session_id = parts[1]
                    # 尝试从 message_obj 获取消息类型
                    if msg_obj:
                        if hasattr(msg_obj, "type"):
                            msg_type = str(msg_obj.type).lower()
                            if "group" in msg_type:
                                return f"群:{session_id}"
                            elif "friend" in msg_type or "private" in msg_type:
                                return "私聊"
                    return origin
                
                return origin

            # 尝试从 message_obj 获取
            if msg_obj:
                if hasattr(msg_obj, "group_id") and msg_obj.group_id:
                    return f"群:{msg_obj.group_id}"
                if hasattr(msg_obj, "type"):
                    msg_type = str(msg_obj.type).lower()
                    if "group" in msg_type:
                        return f"群:{msg_obj.session_id}"
                    elif "friend" in msg_type or "private" in msg_type:
                        return "私聊"

            return "未知"
        except Exception as e:
            logger.error(f"[查证器] 获取来源群失败: {e}")
            return "未知"

    def _get_help_text(self) -> str:
        return (
            "📋 查证器插件使用帮助\n"
            "─" * 20 + "\n"
            "📌 基本用法（查证）:\n"
            "  回复某条消息 → 发送: /查证 或 /测谎\n\n"
            "📊 统计查询:\n"
            "  /查证 统计 → 查看全服可信度排行榜\n"
            "  /查证 统计 @用户 → 查看某用户历史均分\n"
            "  /测谎 统计 → 同上（别名）\n\n"
            "🔧 管理员命令:\n"
            "  /查证 重置 @用户 → 清除某用户所有数据\n"
            "  /测谎 重置 @用户 → 同上（别名）\n\n"
            "📖 其他:\n"
            "  /查证 帮助 或 /测谎 帮助 → 显示本帮助\n\n"
            "💡 提示: 先引用（回复）一条消息，再发送 /查证 或 /测谎 即可分析！\n"
            "🖥️ WebUI: 在插件详情页可打开管理面板查看和编辑所有记录"
        )
