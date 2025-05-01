"""
Этот скрипт использует LangChain, OpenAI и Chroma для создания ИИ-агента,
который отвечает на вопросы о компании AI-One.

Основные этапы:
1. Скрапинг текста с веб-страницы компании.
2. Разбиение текста на части и сохранение в векторное хранилище Chroma.
3. Создание инструмента поиска (retriever) для поиска информации о компании.
4. Настройка агента, который взаимодействует с пользователем, используя модель OpenAI.
5. Определение графа состояний агента с помощью LangGraph.
6. Запуск агента в асинхронном режиме для обработки входных сообщений.
"""

from langchain.docstore.document import Document
from langchain.text_splitter import CharacterTextSplitter
from langchain.embeddings import OpenAIEmbeddings
from langchain_openai import ChatOpenAI
from langchain_community.vectorstores import Chroma
from langchain.tools.retriever import create_retriever_tool
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage, ToolMessage
from langchain_core.runnables import RunnableLambda
from langgraph.graph import END, StateGraph

import operator
import requests
import os
from typing import Annotated, Sequence, TypedDict, Union, List, Dict
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()
os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY")
os.environ["LANGCHAIN_TRACING_V2"] = "true"
os.environ["LANGCHAIN_API_KEY"] = os.getenv("LANGCHAIN_API_KEY")
os.environ["LANGCHAIN_PROJECT"] = "ai-one"

def scrape_text(url: str):
    """
    Функция для скрапинга текста с веб-страницы.
    :param url: Ссылка на веб-страницу.
    :return: Список документов с разбитым на части текстом или сообщение об ошибке.
    """
    try:
        response = requests.get(url)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            page_text = soup.get_text(separator=" ", strip=True)
            source_chunks = []
            splitter = CharacterTextSplitter(separator=" ", chunk_size=1000, chunk_overlap=100)
            for chunk in splitter.split_text(page_text):
                source_chunks.append(Document(page_content=chunk, metadata={'source': url}))
            return source_chunks
        else:
            return f"Failed to retrieve the webpage. Status code: {response.status_code}"
    except Exception as error:
        print(error)
        return f"Failed to retrieve the webpage: {error}"

# Получение информации о компании
target_url = "https://xn--80aa2aprbbg3bd2dub.xn--p1ai/deti/drugoyedetstvo/"
about_company = scrape_text(target_url)

# Создание векторного представления текста
embeddings = OpenAIEmbeddings()
vectorstore_about_company = Chroma.from_documents(documents=about_company, embedding=embeddings)
retriever_about_company = vectorstore_about_company.as_retriever()

# Создание инструмента поиска по информации о компании
about_company_tool = create_retriever_tool(
    retriever_about_company,
    "retriever_about_company",
    "Отвечай на вопросы о компании и ее продуктах."
)

tools = [about_company_tool]
openai = ChatOpenAI(model="gpt-4o-mini")
model = openai.bind_tools(tools)

# Определение состояния агента
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], operator.add]
    response: List[Dict[str, Union[str, None]]]

def should_continue(state):
    """
    Определяет, нужно ли продолжать выполнение агента.
    """
    return "continue" if state["messages"][-1].tool_calls else 'end'

async def call_model(state, config):
    """
    Вызывает модель OpenAI для обработки сообщений.
    """
    response = await model.ainvoke(state["messages"], config=config)
    return {"messages": [response]}

def _invoke_tool(tool_call):
    """
    Выполняет вызов инструмента поиска информации о компании.
    """
    tool = {tool.name: tool for tool in tools}[tool_call["name"]]
    return ToolMessage(tool.invoke(tool_call["args"]), tool_call_id=tool_call["id"])

tool_executor = RunnableLambda(_invoke_tool)

def call_tools(state):
    """
    Обрабатывает вызовы инструментов.
    """
    last_message = state["messages"][-1]
    return {"messages": tool_executor.batch(last_message.tool_calls)}

# Создание графа состояний агента
workflow = StateGraph(AgentState)
workflow.add_node("agent", call_model)
workflow.add_node("action", call_tools)
workflow.set_entry_point("agent")
workflow.add_conditional_edges("agent", should_continue, {"continue": "action", "end": END})
workflow.add_edge("action", "agent")
graph = workflow.compile()

async def agent_start(input):
    """
    Запуск агента для обработки входящих сообщений.
    """
    async for msg, metadata in graph.astream(input, stream_mode="messages"):
        if msg.content and not isinstance(msg, HumanMessage) and isinstance(msg, AIMessage):
            yield (msg.content)
