"""
Triage Risk Scoring Model
=========================
โค้ดนี้แปลงไดอะแกรมที่ให้มาให้เป็นโปรแกรม Python จริง

โครงสร้างของโมเดล (ตามไดอะแกรม):

    X1, X2, X3  --(น้ำหนัก W1..W4)-->  --(ค่าเบี่ยงเบน B1..B4)-->  Z  --> Y1, Y2

หมายเหตุ: ไดอะแกรมมีอินพุตแค่ X1-X3 (ไม่มี X4) แต่มี W1-W4 และ B1-B4
เนื่องจาก W4 (Age Weight) ดึงอายุมาจาก X3 อยู่แล้ว ส่วน B1-B4 เป็นค่า
เบี่ยงเบนเชิงระบบ/บริบท (bias) ที่ไม่ได้ผูกกับ X ตัวใดตัวหนึ่งโดยตรง
แต่มาจากพารามิเตอร์แวดล้อม (operational context) เช่น เวลา, ความหนาแน่น
ของ รพ., ความมั่นใจของ AI และจำนวนยาที่ใช้ร่วม

- X1  Physiological Data      : สัญญาณชีพ + ความเสี่ยงทางร่างกาย
- X2  Subjective/Patient      : คะแนนความปวด + ข้อมูลจากแอปที่ผู้ป่วยกรอกเอง
- X3  AI Contextual/Demo      : คีย์เวิร์ดความเสี่ยงจาก AI parser + อายุ/เพศ

- W1  Vital Signs Weight      : เพิ่มน้ำหนักถ้าสัญญาณชีพหลุด abnormal range
- W2  Pain Score Weight       : ปรับให้สอดคล้อง/cross-validate กับ X3
- W3  Risk-Keyword Weight     : auto-scale ขึ้นเป็นพิเศษถ้าเจอคีย์เวิร์ดวิกฤต
- W4  Age Weight              : เพิ่มน้ำหนักให้กลุ่มเสี่ยงสูง (เด็กเล็ก/ผู้สูงอายุ)
                                 (ดึงอายุจาก X3 โดยตรง ไม่มี X4 แยก)

- B1  Safe-Fail Bias          : บวกค่าคงที่เสมอ เอนเอียงไปทาง over-estimate
                                 ความเสี่ยง เพื่อลด False Negative
- B2  Capacity Bias           : ปรับตามความหนาแน่นของ ER/รพ. แบบ real-time
- B3  AI Audit Bias           : ลดความมั่นใจ (ถอยเป็นลบ) ถ้า confidence ต่ำ
                                 หรือพบ polypharmacy
- B4  Time-Context Bias       : เพิ่มความเข้มงวดช่วงเวลาที่บุคลากรจำกัด
                                 (เช่น กะดึก)

- Z   ผลรวมข้อมูล (weighted sum ของ X*W บวกกับผลรวมของ B ทั้งหมด)
- Y1  ระดับความเสี่ยง (risk level)
- Y2  คำแนะนำการดำเนินการ (recommended action)
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List


# ---------------------------------------------------------------------------
# 1) โครงสร้างข้อมูลนำเข้า (X1-X3)
# ---------------------------------------------------------------------------

@dataclass
class VitalSigns:
    """X1: Physiological Data"""
    heart_rate: float          # bpm
    resp_rate: float           # breaths/min
    temp_c: float              # องศาเซลเซียส
    spo2: float                # %
    systolic_bp: float         # mmHg

    def abnormality_score(self) -> float:
        """คำนวณคะแนนความผิดปกติของสัญญาณชีพ (0 = ปกติ, ยิ่งสูงยิ่งผิดปกติ)"""
        score = 0.0
        if not (60 <= self.heart_rate <= 100):
            score += min(abs(self.heart_rate - 80) / 20, 3.0)
        if not (12 <= self.resp_rate <= 20):
            score += min(abs(self.resp_rate - 16) / 4, 3.0)
        if not (36.1 <= self.temp_c <= 37.5):
            score += min(abs(self.temp_c - 37.0), 3.0)
        if self.spo2 < 95:
            score += min((95 - self.spo2) / 2, 4.0)
        if not (90 <= self.systolic_bp <= 140):
            score += min(abs(self.systolic_bp - 115) / 15, 3.0)
        return round(score, 2)


@dataclass
class PatientReported:
    """X2: Subjective & Patient Reported"""
    pain_score: int             # 0-10
    app_symptom_flags: List[str] = field(default_factory=list)  # อาการที่กรอกในแอป

    def subjective_score(self) -> float:
        base = self.pain_score / 10 * 5.0   # scale เป็น 0-5
        base += 0.5 * len(self.app_symptom_flags)
        return round(base, 2)


@dataclass
class AIContext:
    """X3: AI Contextual & Demographic (รวมอายุ/เพศไว้ในนี้ ไม่มี X4 แยก)"""
    risk_keywords: List[str] = field(default_factory=list)  # จาก AI parser (JSON)
    age: int = 30
    gender: str = "unknown"

    CRITICAL_KEYWORDS = {"เจ็บหน้าอก", "หายใจไม่ออก", "ปากเบี้ยว", "ชักเกร็ง"}

    def keyword_score(self) -> float:
        score = 0.0
        for kw in self.risk_keywords:
            score += 2.0 if kw in self.CRITICAL_KEYWORDS else 0.5
        return round(score, 2)

    def has_critical_keyword(self) -> bool:
        return any(kw in self.CRITICAL_KEYWORDS for kw in self.risk_keywords)


@dataclass
class OperationalContext:
    """
    พารามิเตอร์แวดล้อม/ระบบ ที่ใช้คำนวณ B2, B3, B4 โดยตรง
    (ไม่ใช่ X input ตามไดอะแกรม แต่เป็น context ที่ bias-layer ต้องใช้)
    """
    medication_count: int = 0     # จำนวนยาที่ใช้ร่วม -> polypharmacy check (B3)
    hour_of_day: int = 12         # 0-23 -> night shift check (B4)
    er_current_load: float = 0.5  # 0.0 (ว่าง) - 1.0 (แน่นสุด) -> capacity bias (B2)
    ai_confidence: float = 0.9    # 0.0-1.0 ความมั่นใจของ AI ที่ประเมิน (B3)


@dataclass
class PatientCase:
    x1_vitals: VitalSigns
    x2_reported: PatientReported
    x3_ai_context: AIContext
    context: OperationalContext = field(default_factory=OperationalContext)


# ---------------------------------------------------------------------------
# 2) น้ำหนัก W1..W4
# ---------------------------------------------------------------------------

def compute_weights(case: PatientCase) -> dict:
    x1_score = case.x1_vitals.abnormality_score()
    x3_score = case.x3_ai_context.keyword_score()

    w1 = 1.0 + min(x1_score * 0.3, 1.5)

    w2 = 1.0
    if case.x2_reported.pain_score >= 7 and x3_score == 0:
        w2 = 0.7
    elif case.x2_reported.pain_score >= 7 and x3_score > 0:
        w2 = 1.2

    w3 = 2.5 if case.x3_ai_context.has_critical_keyword() else 1.0

    age = case.x3_ai_context.age
    w4 = 1.5 if (age >= 65 or age < 5) else 1.0

    return {"W1": round(w1, 2), "W2": round(w2, 2),
            "W3": round(w3, 2), "W4": round(w4, 2)}


# ---------------------------------------------------------------------------
# 3) ค่าเบี่ยงเบน B1..B4
# ---------------------------------------------------------------------------

def compute_biases(case: PatientCase) -> dict:
    ctx = case.context

    b1 = 1.0
    b2 = round(ctx.er_current_load * 1.5, 2)

    b3 = 0.0
    if ctx.ai_confidence < 0.6:
        b3 -= 0.5
    if ctx.medication_count >= 5:
        b3 -= 0.3
    b3 = round(b3, 2)

    hour = ctx.hour_of_day
    b4 = 1.0 if (hour >= 22 or hour < 6) else 0.0

    return {"B1": b1, "B2": b2, "B3": b3, "B4": b4}


# ---------------------------------------------------------------------------
# 4) Z: ผลรวมข้อมูล
# ---------------------------------------------------------------------------

def compute_z(case: PatientCase, weights: dict, biases: dict) -> float:
    x1_score = case.x1_vitals.abnormality_score()
    x2_score = case.x2_reported.subjective_score()
    x3_score = case.x3_ai_context.keyword_score()

    weighted_sum = (
        weights["W1"] * x1_score
        + weights["W2"] * x2_score
        + weights["W3"] * x3_score
        + (weights["W4"] - 1.0) * (x1_score + x2_score + x3_score) * 0.2
    )
    total_bias = sum(biases.values())
    z = weighted_sum + total_bias
    return round(z, 2)


# ---------------------------------------------------------------------------
# 5) Y1, Y2: ผลลัพธ์สุดท้าย
# ---------------------------------------------------------------------------

class RiskLevel(str, Enum):
    LOW = "ความเสี่ยงต่ำ"
    MODERATE = "ความเสี่ยงปานกลาง"
    HIGH = "ความเสี่ยงสูง"
    CRITICAL = "วิกฤต"


def compute_outputs(z: float, biases: dict) -> tuple:
    if z < 3:
        y1 = RiskLevel.LOW
    elif z < 6:
        y1 = RiskLevel.MODERATE
    elif z < 10:
        y1 = RiskLevel.HIGH
    else:
        y1 = RiskLevel.CRITICAL

    if y1 == RiskLevel.CRITICAL:
        y2 = "ส่งพบแพทย์ทันที (Emergency) — แจ้งทีมฉุกเฉิน"
    elif y1 == RiskLevel.HIGH:
        y2 = "ให้แพทย์ตรวจด่วนภายใน 15 นาที"
        if biases["B2"] > 1.0:
            y2 += " (รพ./ER แน่น: พิจารณา escalate หรือส่งต่อ)"
    elif y1 == RiskLevel.MODERATE:
        y2 = "รอตรวจตามคิวปกติ พร้อมติดตามอาการซ้ำใน 30-60 นาที"
    else:
        y2 = "นัดตรวจ OPD หรือให้คำแนะนำดูแลตนเองที่บ้าน"

    return y1, y2


# ---------------------------------------------------------------------------
# 6) รวมทุกขั้นตอนเป็นฟังก์ชันเดียว
# ---------------------------------------------------------------------------

def run_triage_model(case: PatientCase) -> dict:
    weights = compute_weights(case)
    biases = compute_biases(case)
    z = compute_z(case, weights, biases)
    y1, y2 = compute_outputs(z, biases)

    return {
        "X_scores": {
            "X1_vital_abnormality": case.x1_vitals.abnormality_score(),
            "X2_subjective": case.x2_reported.subjective_score(),
            "X3_keyword": case.x3_ai_context.keyword_score(),
        },
        "W": weights,
        "B": biases,
        "Z": z,
        "Y1_risk_level": y1.value,
        "Y2_recommendation": y2,
    }


# ---------------------------------------------------------------------------
# 7) ตัวอย่างการใช้งาน
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    case = PatientCase(
        x1_vitals=VitalSigns(
            heart_rate=118, resp_rate=24, temp_c=38.6, spo2=92, systolic_bp=88
        ),
        x2_reported=PatientReported(
            pain_score=8, app_symptom_flags=["เวียนหัว", "ใจสั่น"]
        ),
        x3_ai_context=AIContext(
            risk_keywords=["เจ็บหน้าอก"], age=72, gender="male"
        ),
        context=OperationalContext(
            medication_count=6, hour_of_day=2, er_current_load=0.9,
            ai_confidence=0.85
        ),
    )

    result = run_triage_model(case)

    print("=== Triage Risk Scoring Model ===")
    for k, v in result.items():
        print(f"{k}: {v}")

