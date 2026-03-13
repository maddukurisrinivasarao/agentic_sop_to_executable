import os
from groq import Groq
#from typing import Union
from anthropic import Anthropic

#Create Client and return, provide execute method
class ClientSingleton:
    _instance = None
    _client = None
    _provider = 'groq'
    _model = "llama-3.3-70b-versatile"
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
    def execute(self, messages, max_tokens=3000,temperature=0.5):
        self.get_llm_client()
        response = self._client.chat.completions.create(
            model=self._model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=messages
        )
        #return response.choices[0].message.content
        return response.choices[0].message
#client1 = ClientSingleton.get_llm_client()
#type(client1)
#res=ClientSingleton.execute(max_tokens=100,temperature=0.4,prompt='hello , what is the date today')
#print(res)