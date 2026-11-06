from typing import Literal
import unicodedata
from pydantic import BaseModel, Field, field_validator, model_validator
from .catalog import BY_ID


class ExpressionChoice(BaseModel):
    id: str
    caption: str = Field(min_length=1, max_length=12)

    @field_validator("id")
    @classmethod
    def known_id(cls, value):
        if value not in BY_ID:
            raise ValueError("未知的表情")
        return value

    @field_validator("caption")
    @classmethod
    def clean_caption(cls, value):
        if any(unicodedata.category(c).startswith("C") for c in value):
            raise ValueError("文案不能包含换行或控制字符")
        if not value.strip():
            raise ValueError("文案不能为空")
        return value.strip()


class PackOptions(BaseModel):
    expressions: list[ExpressionChoice] = Field(min_length=1, max_length=8)
    style: Literal["real", "chibi", "pixel"] = "chibi"
    motion: Literal["jump", "sway", "breathe"] = "jump"
    ink: Literal["dark", "coral", "purple"] = "dark"
    consent: bool = False

    @model_validator(mode="after")
    def unique_expressions(self):
        if len({x.id for x in self.expressions}) != len(self.expressions):
            raise ValueError("每个表情只能选择一次")
        if len({x.caption for x in self.expressions}) != len(self.expressions):
            raise ValueError("开源导出器要求文案不能重复")
        return self
