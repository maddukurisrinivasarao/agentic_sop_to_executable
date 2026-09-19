import os
from types import SimpleNamespace
from groq import Groq
#from typing import Union
from anthropic import Anthropic

#Create Client and return, provide execute method
class ClientSingleton:
    _instance = None
    _client = None
    _provider = 'groq'
    _model = "openai/gpt-oss-120b"

    # Cumulative token usage across every execute() call since the last
    # reset_usage() — this is what the token-budget in sop_autoresearch.md
    # is measured against, since provider rate limits (Groq's TPM/TPD) are
    # the real constraint on how many experiments fit in a session, not an
    # arbitrary experiment count.
    _usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    @classmethod
    def get_llm_client(self):
        if self._instance is None:
            self._instance = self()
            print("Creating new Groq client instance...")
            # This is where the client is initialized once
            if self._provider == 'groq':
                #my_api_key = os.environ.get('GROQ_API_KEY')
                my_api_key = os.environ.get('GROQ_API_KEY_2')
                self._client = Groq(api_key=my_api_key)
            elif self._provider == 'anthropic':
                my_api_key = os.environ.get('ANTHROPIC_API_KEY')
                self._client = Anthropic(api_key=my_api_key)
            else:
                raise ValueError("Invalid client name. Valid client names are groq and anthropic")

        return self._client

    @classmethod
    def execute(self, messages, max_tokens=2000, temperature=0.5):
        self.get_llm_client()
        if self._provider == 'anthropic':
            response = self._client.messages.create(
                model=self._model,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=messages,
            )
            usage = getattr(response, "usage", None)
            if usage is not None:
                prompt_tokens = getattr(usage, "input_tokens", 0) or 0
                completion_tokens = getattr(usage, "output_tokens", 0) or 0
                self._record_usage(prompt_tokens, completion_tokens)
            # Every agent's parsing code assumes `response.content` is a
            # plain string (that's what Groq's `.message` gives them below);
            # Anthropic's SDK returns a list of content blocks with `.text`
            # instead, so normalize to the same shape here rather than
            # making every agent branch on provider.
            return SimpleNamespace(content=response.content[0].text)

        response = self._client.chat.completions.create(
            model=self._model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=messages
        )
        usage = getattr(response, "usage", None)
        if usage is not None:
            self._record_usage(
                getattr(usage, "prompt_tokens", 0) or 0,
                getattr(usage, "completion_tokens", 0) or 0,
            )
        #return response.choices[0].message.content
        return response.choices[0].message

    @classmethod
    def _record_usage(self, prompt_tokens: int, completion_tokens: int) -> None:
        self._usage["prompt_tokens"] += prompt_tokens
        self._usage["completion_tokens"] += completion_tokens
        self._usage["total_tokens"] += prompt_tokens + completion_tokens

    @classmethod
    def get_usage(self) -> dict:
        """Cumulative token usage since the last reset_usage()."""
        return dict(self._usage)

    @classmethod
    def reset_usage(self) -> None:
        self._usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
#client1 = ClientSingleton.get_llm_client()
#type(client1)
#res=ClientSingleton.execute(max_tokens=100,temperature=0.4,prompt='hello , what is the date today')
#print(res)