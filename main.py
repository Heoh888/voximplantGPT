import asyncio
import re
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, AIMessage
from Agent import agent_start

app = FastAPI()

# Регулярное выражение для разделения текста на фразы по символам !, . , ? и запятые
SENTENCE_PATTERN = re.compile(r'[^!.,?]*[!.,?]')

# История сообщений, содержащая системное приветственное сообщение
messages = {
    "messages": [
        SystemMessage(
             """Ты — консультант компании langchain.
             Отвечай так, как будто говоришь по телефону: кратко, ясно, без лишних деталей, но не упуская суть.
             Не используй списки, хештеги и markdown разметку. Только текст и знаки препинания такие как (.!,?).
             """),
    ]
}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    Веб-сокет обработчик, обрабатывающий соединение с клиентом.
    Получает текстовые сообщения, передает их агенту и отправляет клиенту сформированные фразы.
    """
    await websocket.accept()
    buffer = ""  # Буфер для накопления текста

    try:
        while True:
            data = await websocket.receive_text()  # Ждем сообщение от клиента
            messages["messages"].append(HumanMessage(data))
            full_text = ""

            async for value in agent_start(messages):
                full_text = full_text + value
                chunk = value
                if chunk:
                    buffer += chunk  # Накопление текста в буфер

                # Собираем фразы с использованием регулярного выражения
                sentences = SENTENCE_PATTERN.findall(buffer)
                if sentences:
                    for sentence in sentences:
                        await websocket.send_text(sentence.strip())  # Отправляем фразу
                        await asyncio.sleep(0.01)
                        buffer = buffer[len(sentence):]  # Очищаем буфер от отправленной фразы

            messages["messages"].append(AIMessage(full_text))  # Добавляем в историю сообщений
    except WebSocketDisconnect as e:
        print(f"WebSocket отключен (код: {e.code})")
        messages["messages"] = messages["messages"][:1]  # Сбрасываем историю диалога
