# test_whatsapp_bot.py

import requests
import json


class WhatsAppBotTester:
    def __init__(self, phone_number_id, access_token):
        self.phone_number_id = phone_number_id
        self.access_token = access_token
        self.api_url = f"https://graph.facebook.com/v18.0/{phone_number_id}/messages"
        self.headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }

    def send_text_message(self, to_phone, text):
        """Отправить текстовое сообщение"""
        payload = {
            "messaging_product": "whatsapp",
            "to": to_phone,
            "type": "text",
            "text": {"body": text}
        }

        response = requests.post(self.api_url, headers=self.headers, json=payload)
        return response.json()

    def send_button_message(self, to_phone, body_text, buttons):
        """Отправить сообщение с кнопками"""
        payload = {
            "messaging_product": "whatsapp",
            "to": to_phone,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": body_text},
                "action": {
                    "buttons": [
                        {
                            "type": "reply",
                            "reply": {
                                "id": btn["id"],
                                "title": btn["title"][:20]
                            }
                        }
                        for btn in buttons[:3]
                    ]
                }
            }
        }

        response = requests.post(self.api_url, headers=self.headers, json=payload)
        return response.json()

    def test_start_command(self, test_phone):
        """Тестировать команду start"""
        print("Testing /start command...")
        result = self.send_text_message(test_phone, "/start")
        print(f"Result: {json.dumps(result, indent=2)}")

    def test_search_flow(self, test_phone):
        """Тестировать поток поиска"""
        print("\nTesting search flow...")

        # Начинаем поиск
        self.send_text_message(test_phone, "Поиск квартир")

        # Выбираем город
        self.send_text_message(test_phone, "Алматы")

        # Выбираем район
        self.send_text_message(test_phone, "Медеуский")

        # Выбираем класс
        self.send_text_message(test_phone, "Комфорт")

        # Выбираем количество комнат
        self.send_text_message(test_phone, "2")

    def test_admin_commands(self, admin_phone):
        """Тестировать админские команды"""
        print("\nTesting admin commands...")

        # Админ панель
        result = self.send_text_message(admin_phone, "Админ")
        print(f"Admin panel: {result}")

        # Статистика
        result = self.send_text_message(admin_phone, "Статистика")
        print(f"Statistics: {result}")


if __name__ == "__main__":
    # Настройки для тестирования
    PHONE_NUMBER_ID = "your-phone-number-id"
    ACCESS_TOKEN = "your-access-token"
    TEST_PHONE = "77001234567"  # Номер для тестирования (без +)

    tester = WhatsAppBotTester(PHONE_NUMBER_ID, ACCESS_TOKEN)

    # Запускаем тесты
    tester.test_start_command(TEST_PHONE)
    # tester.test_search_flow(TEST_PHONE)
    # tester.test_admin_commands(TEST_PHONE)
