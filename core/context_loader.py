BASE_SYSTEM_PROMPT = (
    "You are a helpful personal assistant running inside a desktop web app."
)

SKILL_REGISTRY: dict[str, dict] = {}


def register_skill(name: str, system_prompt: str, tools: list[dict]) -> None:
    SKILL_REGISTRY[name] = {"system_prompt": system_prompt, "tools": tools}


def build_context(skills: list[str]) -> dict:
    system_prompt = BASE_SYSTEM_PROMPT
    tools: list[dict] = []

    for skill_name in skills:
        skill = SKILL_REGISTRY.get(skill_name)
        if skill is None:
            continue
        system_prompt += "\n\n" + skill["system_prompt"]
        tools.extend(skill["tools"])

    return {"system_prompt": system_prompt, "tools": tools}
