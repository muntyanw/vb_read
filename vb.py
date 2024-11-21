
import time
import signal
from pynput import keyboard  # Для перехвата нажатия клавиш
import threading  # Для запуска слушателя клавиатуры в отдельном потоке
from screen_region import *
from recognize_text import capture_and_recognize
from find_message import *
import time

old_text = ""

# Настройка логирования
logging.basicConfig(
    level=logging.DEBUG,  # Уровень логирования DEBUG для подробной информации
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('vbtofb.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

def send_to_telegram(message):
    # Ваша реализация отправки сообщения в Telegram
    logging.info(f"Отправка сообщения в Telegram:\n{message}")
    pass  # Здесь должен быть ваш код отправки


def main():
    logging.info("Запуск программы")

    # Load initial region from JSON
    left, top, width, height = read_region_from_json()
    region = [left, top, width, height]
    logging.debug(f"Область для захвата: {region}")

    # Draw the initial rectangle on screen
    root = draw_rectangle_on_screen(*region)

    # Prompt user to position Viber under the rectangle
    print(
        "Подгоните окно Viber под красный прямоугольник и нажмите 'Enter' в консоли, или введите 'r' и нажмите 'Enter' для выбора новой области.")
    user_input = input().strip().lower()

    # Handle region selection logic
    if user_input == 'r':
        root.destroy()
        left, top, width, height = select_region()
        region[:] = [left, top, width, height]
        save_region_to_json(left, top, width, height)
        root = draw_rectangle_on_screen(*region)
        print("Подгоните окно Viber под новый красный прямоугольник и нажмите 'Enter' в консоли.")
        input()
    root.destroy()
    logging.debug("Окно с прямоугольником закрыто.")

    # Reset current text after region update
    old_text = load_previous_text()
    logging.debug(f"[main] old_text: {old_text}.")

    running = True
    region_lock = threading.Lock()

    def signal_handler(sig, frame):
        nonlocal running
        logging.info("Получен сигнал завершения. Остановка программы.")
        running = False

    signal.signal(signal.SIGINT, signal_handler)

    # Define function to handle 'r' key press for region update
    def on_press(key):
        try:
            if key.char == 'r':
                logging.info("Нажата клавиша 'r' для изменения области экрана.")
                with region_lock:
                    left, top, width, height = select_region()
                    region[:] = [left, top, width, height]
                    save_region_to_json(left, top, width, height)
                    root = draw_rectangle_on_screen(*region)
                    print("Подгоните окно Viber под новый красный прямоугольник и нажмите 'Enter' в консоли.")
                    input()
                    root.destroy()
                    logging.debug("Окно с новым прямоугольником закрыто.")
                    time.sleep(3)
                    # Reset current text after region update
                    old_text = capture_and_recognize(region)
                    logging.debug(f"[main] old_text: {old_text}.")
                    save_current_text(old_text)

        except AttributeError:
            pass  # Ignore non-character key presses

    # Start keyboard listener in a separate thread
    listener = keyboard.Listener(on_press=on_press)
    listener.start()

    try:
        while running:
            with region_lock:
                # Capture and recognize text from the selected region
                new_text = capture_and_recognize(region)

            if new_text and new_text != old_text:
                logging.debug("Обнаружено изменение в тексте.")
                added_text = find_addition(old_text, new_text)
                if added_text:
                    logging.info(f"Отправка нового текста в Telegram: {added_text}")
                    send_to_telegram(added_text)
                    old_text = new_text
                    save_current_text(old_text)
                else:
                    logging.warning("Не удалось определить добавленный текст.")
            else:
                logging.debug("Изменений в тексте не обнаружено.")

            # Delay before the next capture
            time.sleep(5)

    except KeyboardInterrupt:
        logging.info("Прерывание программы пользователем.")
    except Exception as e:
        logging.error(f"Произошла ошибка: {e}")
    finally:
        save_current_text(new_text)
        listener.stop()
        logging.info("Программа завершена.")


if __name__ == '__main__':
    main()
