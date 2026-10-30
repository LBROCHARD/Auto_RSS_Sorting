"""A provider returning canned responses, so tests never call an LLM."""

from auto_rss_sorting.llm import Completion


class FakeProvider:
    """Returns the canned items in order: a text is returned as the response,
    an exception is raised. Records every (system, user) call."""

    def __init__(self, responses: list[str | Exception]) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str) -> Completion:
        self.calls.append((system, user))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return Completion(
            text=response, input_tokens=100, output_tokens=20, latency_seconds=0.5
        )
