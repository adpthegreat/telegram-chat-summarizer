from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage


class Summarizer:
    def __init__(self, google_api_key):
        self.llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash-lite",
            google_api_key=google_api_key,
        )

    def summarize(self, text_to_summarize, summarization_prompt, **format_kwargs):
        prompt = summarization_prompt.format(text_to_summarize=text_to_summarize, **format_kwargs)
        response = self.llm.invoke([HumanMessage(content=prompt)])
        return response.content, None

    @staticmethod
    def validate_summarization_prompt(summarization_prompt):
        if "{text_to_summarize}" not in summarization_prompt:
            raise RuntimeError("Summarization prompt should include \"{text_to_summarize}\"")
