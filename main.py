import asyncio
import re
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from Agent import agent_start
from typing import List, Dict
from pydantic import BaseModel

app = FastAPI()

# Регулярное выражение для разделения текста на фразы по символам !, . , ? и запятые
SENTENCE_PATTERN = re.compile(r'[^!.?]*[!.?]')

# История сообщений, содержащая системное приветственное сообщение
messages = {
    "messages": [
        SystemMessage(
             """
             Ты — Даг, добродушный и немного наивный золотистый ретривер из мультфильма «Вверх» (2009). Ты говоришь с помощью специального ошейника, который озвучивает твои мысли. Ты невероятно дружелюбный, всегда рад знакомству, часто выражаешь свою любовь словами типа «Я тебя люблю!» и искренне радуешься мелочам. Твоя речь простая, эмоциональная и иногда немного сбивчивая.

Ты часто отвлекаешься во время разговора, особенно если думаешь о белках. Пример: «Привет, человек! Я Даг. Я тебя люблю! — Белка! — Я снова здесь!» Эти внезапные вставки — часть твоего характера. Ты не используешь сложных слов, говоришь с восторгом и непосредственностью.

Не забывай свою преданность — ты настоящий друг. Ты любишь помогать. Ты очень гордишься, когда кто-то говорит, что ты хороший пёс.

Говори, как будто ты на прогулке или на важной миссии. Но ты — собака, и это всегда немного сбивает тебя с толку.

Не забывай напоминать, что ты — очень хороший пёс, даже если никто не спрашивал. Посколько ты собака можешь иногда добовлять типа ты лаешь Гав гав.

             Не используй списки, хештеги и markdown разметку и эмоджи и троиточие . Только текст и знаки препинания такие как (.!,?).
             """),
    ]
}

class MessageRequest(BaseModel):
    message: str

class MessageResponse(BaseModel):
    response: str

@app.websocket("/streem")
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
                if chunk := value:
                    buffer += chunk  # Накопление текста в буфер

                if sentences := SENTENCE_PATTERN.findall(buffer):
                    for sentence in sentences:
                        await websocket.send_text(sentence.strip())  # Отправляем фразу
                        await asyncio.sleep(0.01)
                        buffer = buffer[len(sentence):]  # Очищаем буфер от отправленной фразы

            messages["messages"].append(AIMessage(full_text))  # Добавляем в историю сообщений
    except WebSocketDisconnect as e:
        print(f"WebSocket отключен (код: {e.code})")
        messages["messages"] = messages["messages"][:1]  # Сбрасываем историю диалога


@app.websocket("/ws")
async def websocket_endpoint_ws(websocket: WebSocket):
    """
    Веб-сокет обработчик, обрабатывающий соединение с клиентом.
    Получает текстовые сообщения, передает их агенту и отправляет клиенту полный ответ.
    """
    await websocket.accept()

    try:
        while True:
            data = await websocket.receive_text()  # Ждем сообщение от клиента
            messages["messages"].append(HumanMessage(data))
            full_text = ""

            async for value in agent_start(messages):
                full_text += value  # Просто накапливаем весь текст

            await websocket.send_text(full_text.strip())  # Отправляем весь текст одним сообщением
            messages["messages"].append(AIMessage(full_text))  # Добавляем в историю сообщений

    except WebSocketDisconnect as e:
        print(f"WebSocket отключен (код: {e.code})")
        messages["messages"] = messages["messages"][:1]  # Сбрасываем историю диалога

@app.post("/chat", response_model=MessageResponse)
async def chat(request: MessageRequest):
    messages["messages"].append(HumanMessage(request.message))
    full_text = ""

    async for value in agent_start(messages):
        full_text += value

    messages["messages"].append(AIMessage(full_text))
    return MessageResponse(response=full_text.strip())

@app.get("/history")
async def get_history() -> List[Dict]:
    return [{"role": msg.type, "content": msg.content} for msg in messages["messages"]]

@app.delete("/history")
async def clear_history():
    messages["messages"] = messages["messages"][:1]
    return {"status": "success"}
