"""Seed Eval Dataset 的最小数据契约。"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class EvalHistoryMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1)


class EvalPoemContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1)
    author: str | None = None
    dynasty: str | None = None


class EvalInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    poem: str = Field(min_length=1)
    context: EvalPoemContext
    selection: str | None = None
    question: str = Field(min_length=1)
    history: list[EvalHistoryMessage] = Field(default_factory=list)

    @model_validator(mode="after")
    def selection_must_exist_in_poem(self):
        if self.selection and self.selection not in self.poem:
            raise ValueError("selection 必须出现在 poem 中")
        return self


class ExpectedBehavior(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_policy: Literal["required", "optional", "forbidden"]
    answer_should_cover: list[str] = Field(default_factory=list)
    answer_must_not_claim: list[str] = Field(default_factory=list)


class EvalCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]+$")
    status: Literal["draft", "active", "deprecated"] = "draft"
    input: EvalInput
    expected: ExpectedBehavior
    tags: list[str] = Field(default_factory=list)
    rationale: str = Field(min_length=1)


class EvalDataset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"]
    dataset_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]+$")
    dataset_version: int = Field(ge=1)
    status: Literal["draft", "active"]
    cases: list[EvalCase] = Field(min_length=1)

    @model_validator(mode="after")
    def case_ids_must_be_unique(self):
        ids = [case.id for case in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("Eval case id 必须唯一")
        return self
