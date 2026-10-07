import argparse
import json
import logging
import os
import shutil
import time
import zipfile

import schedule


class Task:
    """Хранит информацию об одной задаче шедулера."""

    def __init__(self, task_id, operation, source, destination=None, schedule_time=None):
        self.task_id = task_id
        self.operation = operation          # 'copy', 'move', 'delete', 'archive'
        self.source = source
        self.destination = destination
        self.schedule_time = schedule_time  # например, 'daily:10:00' или 'weekly:monday:09:00'

    def __repr__(self):
        return (f"<Task id={self.task_id}, operation={self.operation}, "
                f"source={self.source}, destination={self.destination}, "
                f"schedule={self.schedule_time}>")

    def to_dict(self):
        """Преобразует задачу в словарь для сохранения в файл."""
        return {
            "task_id": self.task_id,
            "operation": self.operation,
            "source": self.source,
            "destination": self.destination,
            "schedule_time": self.schedule_time,
        }

    @classmethod
    def from_dict(cls, data):
        """Восстанавливает задачу из словаря, прочитанного из файла."""
        return cls(
            data["task_id"],
            data["operation"],
            data["source"],
            data.get("destination"),
            data.get("schedule_time"),
        )


class FileOperations:
    """Выполняет операции над файлами: копирование, перемещение, удаление, архивирование."""

    @staticmethod
    def copy(source, destination):
        if not destination:
            raise ValueError("для операции copy нужно указать --destination")
        shutil.copy(source, destination)

    @staticmethod
    def move(source, destination):
        if not destination:
            raise ValueError("для операции move нужно указать --destination")
        shutil.move(source, destination)

    @staticmethod
    def delete(source):
        os.remove(source)

    @staticmethod
    def archive(source, destination):
        if not destination:
            raise ValueError("для операции archive нужно указать --destination")
        with zipfile.ZipFile(destination, "w") as archive_file:
            archive_file.write(source, os.path.basename(source))


class Logger:
    """Журналирует выполнение задач: дата, время и статус."""

    def __init__(self, log_file="scheduler.log"):
        logging.basicConfig(
            filename=log_file,
            level=logging.INFO,
            format="%(asctime)s - %(message)s",
        )

    def log_task(self, task, status):
        message = f"Задача {task.task_id} ({task.operation}, {task.source}) - {status}"
        logging.info(message)
        print(message)


class Scheduler:
    """Хранит список задач, сохраняет их в файл и запускает выполнение по расписанию."""

    def __init__(self, tasks_file="tasks.json"):
        self.tasks_file = tasks_file
        self.tasks = []
        self.next_id = 1
        self.logger = Logger()
        self._load_tasks()


    def _load_tasks(self):
        if not os.path.exists(self.tasks_file):
            return
        try:
            with open(self.tasks_file, "r", encoding="utf-8") as f:
                raw_tasks = json.load(f)
        except (json.JSONDecodeError, OSError) as error:
            print(f"Не удалось прочитать {self.tasks_file}: {error}")
            return

        for raw_task in raw_tasks:
            task = Task.from_dict(raw_task)
            self.tasks.append(task)
            self._register_schedule(task)
            if task.task_id >= self.next_id:
                self.next_id = task.task_id + 1

    def _save_tasks(self):
        data = [task.to_dict() for task in self.tasks]
        with open(self.tasks_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def add_task(self, operation, source, destination=None, schedule_time=None):
        task = Task(self.next_id, operation, source, destination, schedule_time)
        self.tasks.append(task)
        self.next_id += 1
        self._register_schedule(task)
        self._save_tasks()
        print(f"Задача добавлена: {task}")
        return task

    def _register_schedule(self, task):
        """Регистрирует задачу в библиотеке schedule по строке расписания."""
        if not task.schedule_time:
            return
        parts = task.schedule_time.split(":")
        try:
            if parts[0] == "daily":
                time_str = ":".join(parts[1:])
                schedule.every().day.at(time_str).do(self.run_task, task)
            elif parts[0] == "weekly":
                day_name = parts[1].lower()
                time_str = ":".join(parts[2:])
                getattr(schedule.every(), day_name).at(time_str).do(self.run_task, task)
            else:
                print(f"Неизвестный тип расписания '{parts[0]}' у задачи {task.task_id} "
                      f"— используйте daily:HH:MM или weekly:день:HH:MM")
        except (IndexError, AttributeError, schedule.ScheduleValueError) as error:
            print(f"Некорректное расписание '{task.schedule_time}' у задачи {task.task_id}: {error}")

    def view_tasks(self):
        if not self.tasks:
            print("Список задач пуст.")
            return
        print("Запланированные задачи:")
        for task in self.tasks:
            print(" ", task)

    def delete_task(self, task_id):
        for task in self.tasks:
            if task.task_id == task_id:
                self.tasks.remove(task)
                self._save_tasks()
                print(f"Задача {task_id} удалена.")
                return
        print(f"Задача с id={task_id} не найдена.")

    def run_task(self, task):
        try:
            if task.operation == "copy":
                FileOperations.copy(task.source, task.destination)
            elif task.operation == "move":
                FileOperations.move(task.source, task.destination)
            elif task.operation == "delete":
                FileOperations.delete(task.source)
            elif task.operation == "archive":
                FileOperations.archive(task.source, task.destination)
            else:
                raise ValueError("неизвестная операция")
            self.logger.log_task(task, "Успешно")
        except Exception as error:
            self.logger.log_task(task, f"Ошибка - {error}")

    def start(self):
        print("Шедулер запущен, ожидание задач по расписанию...")
        while True:
            schedule.run_pending()
            time.sleep(1)


def main():
    scheduler = Scheduler()

    parser = argparse.ArgumentParser(description="Файловый шедулер")
    parser.add_argument("command", help="Команда: add, view, delete, start")
    parser.add_argument("--operation", help="Операция: copy, move, delete, archive")
    parser.add_argument("--source", help="Путь к исходному файлу")
    parser.add_argument("--destination", help="Путь назначения (для copy, move, archive)")
    parser.add_argument("--schedule", help="Расписание, например daily:10:00 или weekly:monday:09:00")
    parser.add_argument("--id", type=int, help="Идентификатор задачи (для delete)")

    args = parser.parse_args()

    if args.command == "add":
        if args.operation and args.source:
            scheduler.add_task(
                operation=args.operation,
                source=args.source,
                destination=args.destination,
                schedule_time=args.schedule,
            )
        else:
            print("Не хватает параметров для добавления задачи")
    elif args.command == "view":
        scheduler.view_tasks()
    elif args.command == "delete":
        if args.id is not None:
            scheduler.delete_task(args.id)
        else:
            print("Укажите --id задачи для удаления")
    elif args.command == "start":
        scheduler.start()
    else:
        print("Неизвестная команда")


if __name__ == "__main__":
    main()
