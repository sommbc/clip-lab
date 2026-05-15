from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import files


@dataclass(frozen=True)
class PromptSpec:
    name: str
    version: str
    template: str

    @property
    def header(self) -> str:
        return f"{self.name}:{self.version}"

    def render(self, payload: str) -> str:
        return f"{self.template.rstrip()}\n\nPROMPT_VERSION: {self.header}\n\n{payload.strip()}\n"


def load_prompt(name: str, version: str = "v1") -> PromptSpec:
    filename = f"{name}.{version}.md"
    template = files(__package__).joinpath("prompts", filename).read_text(encoding="utf-8")
    return PromptSpec(name=name, version=version, template=template)


CANDIDATE_MINING_PROMPT = load_prompt("candidate_mining")
CRITIC_EDITOR_PROMPT = load_prompt("critic_editor")
PACKAGING_PROMPT = load_prompt("packaging")

# Backwards-compatible names for downstream imports.
CLIP_GENERATOR_PROMPT = CANDIDATE_MINING_PROMPT.template
CLIP_CRITIC_PROMPT = CRITIC_EDITOR_PROMPT.template
