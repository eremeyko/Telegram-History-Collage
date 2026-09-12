import asyncio
import random
import tomllib
from pathlib import Path

from telethon import TelegramClient, functions, types
from telethon.errors import RPCError, FloodWaitError


CONFIG_FILE = (
    Path(__file__).resolve().parent
    / "config.toml"
)


def load_config():
    with CONFIG_FILE.open("rb") as file:
        return tomllib.load(file)


config = load_config()

API_ID = config["api_id"]
API_HASH = config["api_hash"]

SESSION_NAME = config.get(
    "session_name",
    "history_junkies"
)

STORIES_DIR = Path(
    config.get(
        "stories_dir",
        "stories"
    )
)

DELAY_SECONDS = config.get(
    "delay_seconds",
    5
)

STORY_PERIOD = config.get(
    "story_period",
    86400
)

PIN_TO_PROFILE = config.get(
    "pin_to_profile",
    True
)

REVERSE_UPLOAD_ORDER = config.get(
    "reverse_upload_order",
    True
)

ASK_CONFIRMATION = config.get(
    "ask_confirmation",
    True
)


# HELPERS
def get_story_files() -> list[Path]:
    """
    Get all story_*.png files from the stories folder.
    """

    files = sorted(
        STORIES_DIR.glob("story_*.png")
    )

    if not files:
        raise FileNotFoundError(
            f"No story_*.png files found in "
            f"{STORIES_DIR.resolve()}"
        )

    return files


def get_private_rules():
    """
    Only the account owner can view the stories.
    """

    return [
        types.InputPrivacyValueAllowUsers(
            users=[
                types.InputUserSelf()
            ]
        )
    ]


def get_public_rules():
    """
    Everyone can view the stories.
    """

    return [
        types.InputPrivacyValueAllowAll()
    ]


async def check_available_slots(
    client: TelegramClient,
    required_count: int,
):
    """
    Check how many stories can still be uploaded.
    """

    result = await client(
        functions.stories.CanSendStoryRequest(
            peer="me"
        )
    )

    available_slots = getattr(
        result,
        "count_remains",
        None,
    )

    if available_slots is None:
        print(
            "Could not get the number of "
            "available story slots."
        )
        print(result.stringify())

        raise RuntimeError(
            "Unknown response format from "
            "stories.canSendStory"
        )

    print(
        f"Available story slots: "
        f"{available_slots}"
    )

    print(
        f"Stories to upload: "
        f"{required_count}"
    )

    if available_slots < required_count:
        raise RuntimeError(
            f"Not enough story slots: "
            f"{available_slots} left, "
            f"but {required_count} are needed."
        )

    print("Story limit check passed.")


async def upload_story(
    client: TelegramClient,
    path: Path,
    privacy_rules,
) -> int:
    """
    Upload one story and return its story_id.
    """

    print(f"Uploading: {path.name}")

    uploaded_file = await client.upload_file(path)

    media = types.InputMediaUploadedPhoto(
        file=uploaded_file
    )

    random_id = random.randrange(
        1,
        2**63 - 1
    )

    result = await client(
        functions.stories.SendStoryRequest(
            peer="me",
            media=media,
            privacy_rules=privacy_rules,
            random_id=random_id,
            period=STORY_PERIOD,
            pinned=PIN_TO_PROFILE,
            noforwards=False,
        )
    )

    story_id = None

    for update in getattr(
        result,
        "updates",
        []
    ):
        if (
            isinstance(
                update,
                types.UpdateStoryID
            )
            and update.random_id == random_id
        ):
            story_id = update.id
            break

    if story_id is None:
        print(result.stringify())

        raise RuntimeError(
            f"Could not get story_id "
            f"for {path.name}"
        )

    print(
        f"Uploaded: {path.name} "
        f"(story_id={story_id})"
    )

    return story_id


async def make_stories_public(
    client: TelegramClient,
    story_ids: list[int],
):
    """
    Make all uploaded stories visible to everyone.
    """

    print()
    print("Making uploaded stories public...")

    public_rules = get_public_rules()

    for index, story_id in enumerate(
        story_ids,
        start=1,
    ):
        while True:
            try:
                await client(
                    functions.stories.EditStoryRequest(
                        peer="me",
                        id=story_id,
                        privacy_rules=public_rules,
                    )
                )

                print(
                    f"[{index}/{len(story_ids)}] "
                    f"Story {story_id} is now public."
                )

                break

            except FloodWaitError as error:
                wait_seconds = error.seconds + 2

                print()
                print(
                    f"Telegram requested a flood wait "
                    f"of {error.seconds} seconds."
                )

                print(
                    f"Waiting {wait_seconds} seconds "
                    f"before retrying story {story_id}..."
                )

                await asyncio.sleep(
                    wait_seconds
                )

            except RPCError as error:
                print(
                    f"Could not make story {story_id} public: "
                    f"{error}"
                )

                print(
                    "Continuing with the next story."
                )

                break

        if index < len(story_ids):
            print(
                f"Waiting {DELAY_SECONDS} seconds "
                f"before the next privacy update..."
            )

            await asyncio.sleep(
                DELAY_SECONDS
            )

    print("Privacy update process finished.")


# MAIN
async def main():
    files = get_story_files()

    if REVERSE_UPLOAD_ORDER:
        files.reverse()

    print("Found files:")

    for index, path in enumerate(
        files,
        start=1
    ):
        print(
            f"  {index:02d}. {path.name}\n\n"
        )

    
    print(
        f"Total stories: {len(files)}"
    )

    print(
        "Stories will be made public after "
        "a successful upload."
    )

    print(
        "Auto-pin after expiration: enabled"
        if PIN_TO_PROFILE
        else "Auto-pin after expiration: disabled"
    )

    print()

    async with TelegramClient(
        SESSION_NAME,
        API_ID,
        API_HASH,
    ) as client:

        me = await client.get_me()

        print(
            f"Account: "
            f"@{me.username or 'no_username'} "
            f"(id={me.id})"
        )

        await check_available_slots(
            client,
            required_count=len(files),
        )

        if ASK_CONFIRMATION:
            answer = input(
                "\nStart uploading? Type YES: "
            ).strip()

            if answer != "YES":
                print("Upload cancelled.")
                return

        privacy_rules = get_private_rules()

        uploaded_story_ids = []
        upload_failed = False
        output_file = (
            STORIES_DIR
            / "uploaded_story_ids.txt"
        )

        for index, path in enumerate(
            files,
            start=1
        ):
            print(
                f"\n[{index}/{len(files)}]"
            )

            try:
                story_id = await upload_story(
                    client=client,
                    path=path,
                    privacy_rules=privacy_rules,
                )

                uploaded_story_ids.append(
                    (
                        path.name,
                        story_id,
                    )
                )

            except RPCError as error:
                print(
                    f"Telegram error while uploading "
                    f"{path.name}: {error}"
                )
                print(
                    "Upload stopped."
                )

                upload_failed = True
                break

            except Exception as error:
                print(
                    f"Error while uploading "
                    f"{path.name}: {error}"
                )
                upload_failed = True
                break

            if index < len(files):
                print(
                    f"Waiting "
                    f"{DELAY_SECONDS} seconds..."
                )

                await asyncio.sleep(
                    DELAY_SECONDS
                )

        upload_completed = (
        not upload_failed
        and len(uploaded_story_ids) == len(files)
    )

        if upload_completed:
            story_ids = [
                story_id
                for _, story_id in uploaded_story_ids
            ]

            try:
                await make_stories_public(
                    client,
                    story_ids,
                )

            except RPCError as error:
                print(
                    f"Could not change story privacy: "
                    f"{error}"
                )
                print(
                    "The stories are still private."
                )

        else:
            print(
                "Upload was not completed. "
                "Stories will remain private."
            )

        output_file.write_text(
            "\n".join(
                f"{filename}\t{story_id}"
                for filename, story_id
                in uploaded_story_ids
            ),
            encoding="utf-8",
        )

        print()
        print(
            f"Done. Successfully uploaded: "
            f"{len(uploaded_story_ids)} "
            f"of {len(files)}"
        )

        print(
            f"Story IDs saved to: "
            f"{output_file.resolve()}"
        )


if __name__ == "__main__":
    asyncio.run(main())

