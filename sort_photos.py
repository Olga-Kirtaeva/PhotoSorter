import argparse
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timedelta
import shutil
import re

from PIL import Image
from PIL.ExifTags import IFD

from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter


# ==========================================================
# ПАПКИ
# ==========================================================

def parse_args():
    parser = argparse.ArgumentParser(
        description="Sort photos into event folders using EXIF dates and GPS data."
    )
    parser.add_argument("--input", type=Path, required=True, help="Source photo folder.")
    parser.add_argument("--output", type=Path, required=True, help="Destination folder.")
    return parser.parse_args()


# ==========================================================
# EXIF И GPS
# ==========================================================

def gps_to_decimal(coordinates, reference):

    degrees = float(coordinates[0])
    minutes = float(coordinates[1])
    seconds = float(coordinates[2])

    decimal = degrees + minutes / 60 + seconds / 3600

    if reference in ("S", "W"):
        decimal *= -1

    return decimal


def get_photo_info(image_path):

    with Image.open(image_path) as image:

        exif = image.getexif()

        exif_ifd = exif.get_ifd(IFD.Exif)
        gps_ifd = exif.get_ifd(IFD.GPSInfo)

        date_taken = exif_ifd.get(36867)

        latitude = None
        longitude = None

        if gps_ifd:

            lat_ref = gps_ifd.get(1)
            lat = gps_ifd.get(2)

            lon_ref = gps_ifd.get(3)
            lon = gps_ifd.get(4)

            if lat and lon:

                latitude = gps_to_decimal(
                    lat,
                    lat_ref
                )

                longitude = gps_to_decimal(
                    lon,
                    lon_ref
                )

        return date_taken, latitude, longitude


# ==========================================================
# НАЗВАНИЕ МЕСТА
# ==========================================================

def get_place_name(location):

    if location is None:
        return None

    address = location.raw.get("address", {})

    city = (
        address.get("city")
        or address.get("town")
        or address.get("village")
        or address.get("municipality")
        or address.get("county")
    )

    return city


# ==========================================================
# СОБЫТИЯ
# ==========================================================

def create_events(photos_by_date):

    dates = sorted(photos_by_date)

    if not dates:
        return []

    events = []

    current_event = [dates[0]]

    for current_date in dates[1:]:

        previous_date = current_event[-1]

        # Если следующий календарный день —
        # считаем продолжением того же события

        if current_date == previous_date + timedelta(days=1):

            current_event.append(current_date)

        else:

            events.append(current_event)

            current_event = [current_date]

    events.append(current_event)

    return events


def format_event_date(event_dates):

    start_date = event_dates[0]
    end_date = event_dates[-1]

    if start_date == end_date:

        return start_date.strftime("%Y-%m-%d")

    return (
        f"{start_date.strftime('%Y-%m-%d')}"
        f"–"
        f"{end_date.strftime('%Y-%m-%d')}"
    )


# ==========================================================
# WINDOWS: УБИРАЕМ НЕДОПУСТИМЫЕ СИМВОЛЫ ИЗ ИМЕНИ ПАПКИ
# ==========================================================

def clean_folder_name(name):

    return re.sub(
        r'[<>:"/\\|?*]',
        "",
        name
    ).strip()


# ==========================================================
# КОПИРОВАНИЕ БЕЗ ПЕРЕЗАПИСИ
# ==========================================================

def safe_copy(source, destination_folder):

    destination_folder.mkdir(
        parents=True,
        exist_ok=True
    )

    destination = (
        destination_folder / source.name
    )

    # Если файл с таким именем уже существует,
    # ничего не перезаписываем

    if destination.exists():

        print(
            f"Уже существует, пропускаю: "
            f"{source.name}"
        )

        return False

    shutil.copy2(
        source,
        destination
    )

    return True


# ==========================================================
# MAIN
# ==========================================================

def main():

    args = parse_args()
    photo_folder = args.input.expanduser().resolve()
    output_folder = args.output.expanduser().resolve()

    if not photo_folder.is_dir():
        raise SystemExit(f"Input folder does not exist: {photo_folder}")

    if photo_folder == output_folder:
        raise SystemExit("Input and output folders must be different.")

    print()
    print("=" * 70)
    print("PHOTOSORTER")
    print("=" * 70)

    all_files = [
        file
        for file in photo_folder.iterdir()
        if file.is_file()
    ]

    jpg_files = [
        file
        for file in all_files
        if file.suffix.lower()
        in (".jpg", ".jpeg")
    ]

    other_files = [
        file
        for file in all_files
        if file.suffix.lower()
        not in (".jpg", ".jpeg")
    ]

    print(
        f"Всего файлов: {len(all_files)}"
    )

    print(
        f"JPG: {len(jpg_files)}"
    )

    print(
        f"Других файлов: {len(other_files)}"
    )

    photos_by_date = defaultdict(list)

    no_date_files = []

    # ------------------------------------------------------
    # ЧИТАЕМ ФОТО
    # ------------------------------------------------------

    for image_path in jpg_files:

        try:

            date_taken, latitude, longitude = (
                get_photo_info(image_path)
            )

            if not date_taken:

                no_date_files.append(
                    image_path
                )

                continue

            date_obj = datetime.strptime(
                date_taken,
                "%Y:%m:%d %H:%M:%S"
            )

            photos_by_date[
                date_obj.date()
            ].append(
                {
                    "file": image_path,
                    "latitude": latitude,
                    "longitude": longitude,
                }
            )

        except Exception as error:

            print(
                f"Ошибка {image_path.name}: "
                f"{error}"
            )

            no_date_files.append(
                image_path
            )

    # ------------------------------------------------------
    # ГРУППИРУЕМ ПО СОБЫТИЯМ
    # ------------------------------------------------------

    events = create_events(
        photos_by_date
    )

    # ------------------------------------------------------
    # ГЕОКОДЕР
    # ------------------------------------------------------

    geolocator = Nominatim(
        user_agent="OlgaPhotoSorter"
    )

    reverse = RateLimiter(
        geolocator.reverse,
        min_delay_seconds=1.1
    )

    output_folder.mkdir(
        parents=True,
        exist_ok=True
    )

    copied_total = 0

    # ------------------------------------------------------
    # ОБРАБАТЫВАЕМ СОБЫТИЯ
    # ------------------------------------------------------

    for number, event_dates in enumerate(
        events,
        start=1
    ):

        event_photos = []

        for date in event_dates:

            event_photos.extend(
                photos_by_date[date]
            )

        places = []

        gps_photos = [
            photo
            for photo in event_photos
            if photo["latitude"] is not None
            and photo["longitude"] is not None
        ]

        # Проверяем максимум 10 GPS-фото
        # одного события

        for photo in gps_photos[:10]:

            try:

                location = reverse(
                    (
                        photo["latitude"],
                        photo["longitude"]
                    ),
                    language="ru"
                )

                place = get_place_name(
                    location
                )

                if (
                    place
                    and place not in places
                ):

                    places.append(place)

            except Exception:

                pass

            # Больше трёх названий
            # в имени папки нам не нужно

            if len(places) >= 3:
                break

        date_text = format_event_date(
            event_dates
        )

        if places:

            place_text = " – ".join(
                places
            )

        else:

            place_text = (
                "место неизвестно"
            )

        folder_name = clean_folder_name(
            f"{date_text} — {place_text}"
        )

        event_folder = (
            output_folder / folder_name
        )

        print()
        print(
            f"СОБЫТИЕ {number}: "
            f"{folder_name}"
        )

        print(
            f"Фотографий: "
            f"{len(event_photos)}"
        )

        for photo in event_photos:

            if safe_copy(
                photo["file"],
                event_folder
            ):

                copied_total += 1

    # ------------------------------------------------------
    # JPG БЕЗ ДАТЫ
    # ------------------------------------------------------

    if no_date_files:

        no_date_folder = (
            output_folder / "Без даты"
        )

        for file in no_date_files:

            if safe_copy(
                file,
                no_date_folder
            ):

                copied_total += 1

    # ------------------------------------------------------
    # НЕ-JPG ФАЙЛЫ
    # ------------------------------------------------------

    if other_files:

        other_folder = (
            output_folder / "Прочие файлы"
        )

        for file in other_files:

            if safe_copy(
                file,
                other_folder
            ):

                copied_total += 1

    # ------------------------------------------------------
    # ИТОГ
    # ------------------------------------------------------

    print()
    print("=" * 70)
    print("ГОТОВО")
    print("=" * 70)

    print(
        f"Создано событий: "
        f"{len(events)}"
    )

    print(
        f"Скопировано файлов: "
        f"{copied_total}"
    )

    print()
    print(
        "Исходные файлы НЕ изменены."
    )

    print()
    print(
        f"Результат находится здесь:\n"
        f"{output_folder}"
    )

    print("=" * 70)


if __name__ == "__main__":
    main()
