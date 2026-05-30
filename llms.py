import os
from dotenv import load_dotenv
from langchain_openai import AzureChatOpenAI

load_dotenv()

chat_llm = AzureChatOpenAI(
    azure_deployment=os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT_NAME"),
    api_key=os.getenv("AZURE_OPENAI_CHAT_KEY"),
    azure_endpoint=os.getenv("AZURE_OPENAI_CHAT_ENDPOINT"),
    model=os.getenv("AZURE_OPENAI_CHAT_MODEL"),
    api_version=os.getenv("AZURE_API_VERSION"),
    temperature=float(os.getenv("LLM_TEMPERATURE", "0.0")),
)