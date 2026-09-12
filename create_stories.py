from pathlib import Path
import argparse
import tomllib

from PIL import Image


CONFIG_FILE = (
    Path(__file__).resolve().parent
    / "config.toml"
)


def load_config():
    with CONFIG_FILE.open("rb") as file:
        return tomllib.load(file)


config = load_config()

STORY_WIDTH = config.get(
    "story_width",
    1080,
)

STORY_HEIGHT = config.get(
    "story_height",
    1920,
)

COLUMNS = config.get(
    "columns",
    3,
)

CONFIG_ROWS = config.get(
    "rows",
    4,
)

PREVIEW_ASPECT = (
    config.get("preview_aspect_width", 196)
    / config.get("preview_aspect_height", 241)
)

FILL = config.get(
    "fill",
    "black",
)

OUTPUT_DIR = Path(
    config.get(
        "output_dir",
        "iphone_stories_3x4",
    )
)


def get_fill_color(fill: str):
    if fill == "black":
        return (0, 0, 0, 255)

    if fill == "transparent":
        return (0, 0, 0, 0)

    raise ValueError(
        f"Unknown fill value: {fill}"
    )


def validate_config():
    if COLUMNS < 1:
        raise ValueError(
            "Columns must be greater than zero."
        )

    if CONFIG_ROWS < 1:
        raise ValueError(
            "Rows must be greater than zero."
        )

    if STORY_WIDTH < 1 or STORY_HEIGHT < 1:
        raise ValueError(
            "Story width and height must be greater than zero."
        )

    if PREVIEW_ASPECT <= 0:
        raise ValueError(
            "Preview aspect must be greater than zero."
        )


def calculate_visible_height() -> int:
    return round(
        STORY_WIDTH / PREVIEW_ASPECT
    )


def calculate_recommended_rows(
    image_width: int,
    image_height: int,
    visible_height: int,
) -> int:
    """
    Calculate the recommended number of rows
    while keeping the configured number of columns.

    The calculation compares the source image aspect ratio
    with the aspect ratio of the visible mosaic area.
    """

    mosaic_width = STORY_WIDTH * COLUMNS

    source_aspect = image_height / image_width

    recommended_rows = round(
        source_aspect
        * mosaic_width
        / visible_height
    )

    return max(1, recommended_rows)


def ask_for_rows(
    recommended_rows: int,
    configured_rows: int,
) -> int:
    if recommended_rows == configured_rows:
        print(
            f"Recommended layout: "
            f"{COLUMNS}x{recommended_rows}"
        )

        return configured_rows

    print()
    print(
        f"Source image is calculated for "
        f"{recommended_rows} rows."
    )

    print(
        f"Configuration currently uses "
        f"{configured_rows} rows."
    )

    print()
    print(
        f"Use recommended layout "
        f"{COLUMNS}x{recommended_rows}?"
    )

    print(
        "Type YES to use the recommended layout."
    )

    print(
        "Press Enter to keep the configuration."
    )

    answer = input("> ").strip()

    if answer == "":
        return configured_rows

    if answer == "YES":
        return recommended_rows

    raise RuntimeError(
        "Generation cancelled by user."
    )


def create_stories(
    input_path: Path,
    output_dir: Path,
):
    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    fill_color = get_fill_color(FILL)

    visible_height = calculate_visible_height()

    top_padding = (
        STORY_HEIGHT - visible_height
    ) // 2

    mosaic_width = STORY_WIDTH * COLUMNS

    with Image.open(input_path) as image:
        image = image.convert("RGBA")

        recommended_rows = calculate_recommended_rows(
            image_width=image.width,
            image_height=image.height,
            visible_height=visible_height,
        )

        rows = ask_for_rows(
            recommended_rows=recommended_rows,
            configured_rows=CONFIG_ROWS,
        )

        mosaic_height = visible_height * rows

        print()
        print(
            f"Original image: "
            f"{image.width}x{image.height}"
        )

        print(
            f"Using layout: "
            f"{COLUMNS}x{rows}"
        )

        print(
            f"Mosaic size: "
            f"{mosaic_width}x{mosaic_height}"
        )

        # Масштабируем изображение по ширине всей мозаики.
        scale = mosaic_width / image.width

        resized_width = mosaic_width
        resized_height = round(
            image.height * scale
        )

        image = image.resize(
            (
                resized_width,
                resized_height,
            ),
            Image.Resampling.LANCZOS,
        )

        # Создаём общую картинку мозаики.
        mosaic = Image.new(
            "RGBA",
            (
                mosaic_width,
                mosaic_height,
            ),
            fill_color,
        )

        mosaic.alpha_composite(
            image,
            (0, 0),
        )

        # Сохраняем цельный предпросмотр.
        save_grid_preview(
            mosaic=mosaic,
            output_dir=output_dir,
            rows=rows,
            visible_height=visible_height,
        )

        total_stories = COLUMNS * rows

        for row in range(rows):
            for col in range(COLUMNS):
                story_number = (
                    row * COLUMNS + col + 1
                )

                left = col * STORY_WIDTH
                top = row * visible_height

                right = left + STORY_WIDTH
                bottom = top + visible_height

                visible_tile = mosaic.crop(
                    (
                        left,
                        top,
                        right,
                        bottom,
                    )
                )

                story = Image.new(
                    "RGBA",
                    (
                        STORY_WIDTH,
                        STORY_HEIGHT,
                    ),
                    fill_color,
                )

                story.alpha_composite(
                    visible_tile,
                    (
                        0,
                        top_padding,
                    ),
                )

                filename = (
                    f"story_{story_number:02d}"
                    f"_r{row + 1}_c{col + 1}.png"
                )

                output_path = (
                    output_dir / filename
                )

                story.save(
                    output_path,
                    format="PNG",
                )

                print(
                    f"[{story_number:02d}/"
                    f"{total_stories}] "
                    f"{filename}"
                )

    print("\nDone.\n")

    print(
        f"Layout: "
        f"{COLUMNS}x{rows}"
        f"Visible area: "
        f"{STORY_WIDTH}x{visible_height}"
        f"Story size: "
        f"{STORY_WIDTH}x{STORY_HEIGHT}"
        f"Top/bottom padding: "
        f"about {top_padding}px"
        f"Output: "
        f"{output_dir.resolve()}"
    )

def save_grid_preview(
    mosaic: Image.Image,
    output_dir: Path,
    rows: int,
    visible_height: int,
):
    """
    Save a preview of the mosaic with gaps between tiles.
    """

    gap = 24

    preview_width = (
        COLUMNS * STORY_WIDTH
        + (COLUMNS - 1) * gap
    )

    preview_height = (
        rows * visible_height
        + (rows - 1) * gap
    )

    preview = Image.new(
        "RGBA",
        (
            preview_width,
            preview_height,
        ),
        (255, 255, 255, 255),
    )

    for row in range(rows):
        for col in range(COLUMNS):
            left = col * STORY_WIDTH
            top = row * visible_height

            right = left + STORY_WIDTH
            bottom = top + visible_height

            tile = mosaic.crop(
                (
                    left,
                    top,
                    right,
                    bottom,
                )
            )

            preview_x = col * (
                STORY_WIDTH + gap
            )

            preview_y = row * (
                visible_height + gap
            )

            preview.alpha_composite(
                tile,
                (
                    preview_x,
                    preview_y,
                ),
            )

    preview_path = (
        output_dir
        / "mosaic_preview_with_gaps.png"
    )

    preview.save(
        preview_path,
        format="PNG",
    )

    print()
    print(
        f"Grid preview saved to: "
        f"{preview_path.resolve()}"
    )

def save_mosaic_preview(
    mosaic: Image.Image,
    output_dir: Path,
):
    preview_path = (
        output_dir
        / "mosaic_preview.png"
    )

    mosaic.save(
        preview_path,
        format="PNG",
    )

    print()
    print(
        f"Mosaic preview saved to: "
        f"{preview_path.resolve()}"
    )

def main():
    validate_config()

    parser = argparse.ArgumentParser(
        description=(
            "Split a photo into Telegram Stories "
            "for an iPhone profile mosaic."
        )
    )

    parser.add_argument(
        "input",
        type=Path,
        help="Path to the source image",
    )

    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=OUTPUT_DIR,
        help="Output folder for the generated Stories",
    )

    args = parser.parse_args()

    if not args.input.is_file():
        raise FileNotFoundError(
            f"File not found: {args.input}"
        )

    create_stories(
        input_path=args.input,
        output_dir=args.output,
    )


if __name__ == "__main__":
    main()