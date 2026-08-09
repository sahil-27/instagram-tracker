import os
import argparse
import base64
import tempfile

import instaloader
from instaloader.exceptions import TooManyRequestsException
from dotenv import load_dotenv

from database import (
    get_current_state,
    save_current_state,
    save_daily_events,
    has_successful_run_today,
    save_successful_run,
)


# ---------------------------------------------------------
# Configuration
# ---------------------------------------------------------

load_dotenv()

TARGET_USERNAME = os.getenv("TARGET_USERNAME")
YOUR_IG_USERNAME = os.getenv("YOUR_IG_USERNAME")

# Local:
# /Users/ssahil/.config/instaloader/session-ammarzair
INSTAGRAM_SESSION_FILE = os.getenv(
    "INSTAGRAM_SESSION_FILE"
)

# Render:
# /etc/secrets/session-ammarzair.b64
INSTAGRAM_SESSION_BASE64_FILE = os.getenv(
    "INSTAGRAM_SESSION_BASE64_FILE"
)


# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------

def compare_users(
    current: list[dict],
    previous: list[dict]
):
    """
    Compare two Instagram user lists using Instagram user IDs.
    """

    current_by_id = {
        user["id"]: user
        for user in current
    }

    previous_by_id = {
        user["id"]: user
        for user in previous
    }

    current_ids = set(current_by_id.keys())
    previous_ids = set(previous_by_id.keys())

    added_ids = current_ids - previous_ids
    removed_ids = previous_ids - current_ids

    added = [
        current_by_id[user_id]
        for user_id in added_ids
    ]

    removed = [
        previous_by_id[user_id]
        for user_id in removed_ids
    ]

    added.sort(
        key=lambda user: user["username"]
    )

    removed.sort(
        key=lambda user: user["username"]
    )

    return added, removed


def print_changes(
    label: str,
    added: list[dict],
    removed: list[dict]
):
    """
    Print detected changes to the terminal.
    """

    print(f"\n📈 {label.upper()} CHANGES")

    print(f"➕ Added ({len(added)}):")

    if added:
        for user in added:
            print(f"   @{user['username']}")
    else:
        print("   None")

    print(f"➖ Removed ({len(removed)}):")

    if removed:
        for user in removed:
            print(f"   @{user['username']}")
    else:
        print("   None")


# ---------------------------------------------------------
# Instagram Session
# ---------------------------------------------------------

def create_session_from_base64_file():
    """
    Read the Base64-encoded Instagram session from a file
    and create a temporary binary session file.

    Used by Render Secret Files.
    """

    if not INSTAGRAM_SESSION_BASE64_FILE:
        return None

    if not os.path.isfile(
        INSTAGRAM_SESSION_BASE64_FILE
    ):
        raise RuntimeError(
            "Instagram Base64 session file not found: "
            f"{INSTAGRAM_SESSION_BASE64_FILE}"
        )

    print(
        "🔐 Preparing Instagram session from "
        "Render Secret File..."
    )

    try:

        with open(
            INSTAGRAM_SESSION_BASE64_FILE,
            "rb"
        ) as f:

            encoded_data = f.read()

        session_data = base64.b64decode(
            encoded_data
        )

    except Exception as e:

        raise RuntimeError(
            f"Could not decode Instagram session: {e}"
        )

    temp_file = tempfile.NamedTemporaryFile(
        prefix="instaloader-session-",
        delete=False
    )

    try:

        temp_file.write(session_data)
        temp_file.close()

        os.chmod(
            temp_file.name,
            0o600
        )

        print(
            "✅ Temporary Instagram session created."
        )

        return temp_file.name

    except Exception:

        temp_file.close()

        try:
            os.unlink(temp_file.name)
        except OSError:
            pass

        raise


def load_instagram_session():
    """
    Load the existing Instaloader session.

    Render:
        INSTAGRAM_SESSION_BASE64_FILE

    Local:
        INSTAGRAM_SESSION_FILE

    Render Secret File takes priority.
    """

    session_file = None
    temporary_session = False

    # -----------------------------------------------------
    # Render Secret File
    # -----------------------------------------------------

    if INSTAGRAM_SESSION_BASE64_FILE:

        session_file = (
            create_session_from_base64_file()
        )

        temporary_session = True

    # -----------------------------------------------------
    # Local session file
    # -----------------------------------------------------

    elif INSTAGRAM_SESSION_FILE:

        session_file = INSTAGRAM_SESSION_FILE

        if not os.path.isfile(session_file):

            raise RuntimeError(
                "Instagram session file not found: "
                f"{session_file}"
            )

    else:

        raise RuntimeError(
            "Neither INSTAGRAM_SESSION_FILE nor "
            "INSTAGRAM_SESSION_BASE64_FILE "
            "is configured."
        )

    loader = instaloader.Instaloader()

    print(
        "🔐 Loading saved Instagram session..."
    )

    try:

        loader.load_session_from_file(
            YOUR_IG_USERNAME,
            session_file
        )

        print(
            f"✅ Logged in as @{YOUR_IG_USERNAME}"
        )

        return (
            loader,
            session_file,
            temporary_session
        )

    except TooManyRequestsException:

        raise RuntimeError(
            "Instagram rate limit detected while "
            "loading the session. "
            "Stopping immediately."
        )

    except Exception as e:

        raise RuntimeError(
            f"Failed to load Instagram session: {e}"
        )


def cleanup_temporary_session(
    session_file: str | None,
    temporary_session: bool
):
    """
    Remove the temporary binary session file.
    """

    if not temporary_session:
        return

    if not session_file:
        return

    try:

        os.unlink(session_file)

        print(
            "🧹 Temporary Instagram session removed."
        )

    except OSError:

        print(
            "⚠️ Could not remove temporary "
            "Instagram session file."
        )


# ---------------------------------------------------------
# Instagram Data
# ---------------------------------------------------------

def fetch_instagram_data(loader):
    """
    Fetch target profile, followers and following.

    A failed request is NEVER treated as an empty list.
    """

    print(
        f"\n📦 Fetching profile for "
        f"@{TARGET_USERNAME}..."
    )

    try:

        profile = instaloader.Profile.from_username(
            loader.context,
            TARGET_USERNAME
        )

        print(
            f"✅ Profile found: "
            f"{profile.full_name or TARGET_USERNAME}"
        )

    except TooManyRequestsException:

        raise RuntimeError(
            "Instagram rate limit detected while "
            "loading the target profile. "
            "Stopping immediately."
        )

    except Exception as e:

        raise RuntimeError(
            f"Could not load profile: {e}"
        )

    # -----------------------------------------------------
    # Followers
    # -----------------------------------------------------

    print(
        "\n📥 Getting followers..."
    )

    try:

        followers = []

        for follower in profile.get_followers():

            followers.append({
                "id": str(follower.userid),
                "username": follower.username
            })

        print(
            f"✅ Retrieved {len(followers)} followers"
        )

    except TooManyRequestsException:

        raise RuntimeError(
            "Instagram rate limit detected while "
            "fetching followers. "
            "Stopping immediately."
        )

    except Exception as e:

        raise RuntimeError(
            f"Could not fetch followers: {e}"
        )

    # -----------------------------------------------------
    # Following
    # -----------------------------------------------------

    print(
        "\n📥 Getting following..."
    )

    try:

        following = []

        for followee in profile.get_followees():

            following.append({
                "id": str(followee.userid),
                "username": followee.username
            })

        print(
            f"✅ Retrieved {len(following)} following"
        )

    except TooManyRequestsException:

        raise RuntimeError(
            "Instagram rate limit detected while "
            "fetching following. "
            "Stopping immediately."
        )

    except Exception as e:

        raise RuntimeError(
            f"Could not fetch following: {e}"
        )

    return profile, followers, following


# ---------------------------------------------------------
# Main
# ---------------------------------------------------------

def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without saving to MongoDB"
    )

    args = parser.parse_args()

    # -----------------------------------------------------
    # Validate configuration
    # -----------------------------------------------------

    if not TARGET_USERNAME:

        raise RuntimeError(
            "TARGET_USERNAME is not configured"
        )

    if not YOUR_IG_USERNAME:

        raise RuntimeError(
            "YOUR_IG_USERNAME is not configured"
        )

    print(
        "=========================================="
    )

    print(
        "          INSTAGRAM TRACKER"
    )

    print(
        "=========================================="
    )

    print(
        f"Target: @{TARGET_USERNAME}"
    )

    print(
        f"Instagram account: @{YOUR_IG_USERNAME}"
    )

    # -----------------------------------------------------
    # Daily safety check
    # -----------------------------------------------------

    if not args.dry_run:

        print(
            "\n🔍 Checking today's tracker status..."
        )

        if has_successful_run_today(
            TARGET_USERNAME
        ):

            print(
                "⏭️ Tracker has already run "
                "successfully today."
            )

            print(
                "🚫 No Instagram requests will be made."
            )

            return

        print(
            "✅ No successful run found for today."
        )

    else:

        print(
            "\n🧪 Dry-run mode: daily safety "
            "check skipped."
        )

    # -----------------------------------------------------
    # Load Instagram session
    # -----------------------------------------------------

    loader = None
    session_file = None
    temporary_session = False

    try:

        (
            loader,
            session_file,
            temporary_session
        ) = load_instagram_session()

    except Exception as e:

        print(
            "\n❌ Instagram session error."
        )

        print(
            f"Reason: {e}"
        )

        return

    try:

        # -------------------------------------------------
        # Fetch Instagram state
        # -------------------------------------------------

        try:

            (
                profile,
                current_followers,
                current_following
            ) = fetch_instagram_data(loader)

        except Exception as e:

            print(
                "\n❌ Tracking run failed."
            )

            print(
                f"Reason: {e}"
            )

            print(
                "\n🚫 Nothing was saved to MongoDB."
            )

            return

        # -------------------------------------------------
        # Get previous state
        # -------------------------------------------------

        print(
            "\n🔍 Loading previous state "
            "from MongoDB..."
        )

        previous_state = get_current_state(
            TARGET_USERNAME
        )

        # -------------------------------------------------
        # First run
        # -------------------------------------------------

        if previous_state is None:

            print(
                "\n🆕 No previous state found."
            )

            print(
                "This is the first run, so this "
                "will become the baseline."
            )

            if args.dry_run:

                print(
                    "\n🚫 Dry run: baseline "
                    "was not saved."
                )

                return

            try:

                save_current_state(
                    TARGET_USERNAME,
                    current_followers,
                    current_following
                )

                save_daily_events(
                    TARGET_USERNAME,
                    [],
                    [],
                    [],
                    []
                )

                save_successful_run(
                    TARGET_USERNAME
                )

                print(
                    "\n✅ Initial state "
                    "saved to MongoDB."
                )

                print(
                    "✅ Tracker run marked "
                    "as successful."
                )

            except Exception as e:

                print(
                    "\n❌ Failed to save "
                    "initial state."
                )

                print(
                    f"Reason: {e}"
                )

                print(
                    "\n⚠️ Run was NOT marked "
                    "as successful."
                )

            return

        # -------------------------------------------------
        # Compare
        # -------------------------------------------------

        print(
            "\n🔍 Comparing with "
            "previous state..."
        )

        previous_followers = previous_state.get(
            "followers",
            []
        )

        previous_following = previous_state.get(
            "following",
            []
        )

        (
            new_followers,
            lost_followers
        ) = compare_users(
            current_followers,
            previous_followers
        )

        (
            new_following,
            unfollowed
        ) = compare_users(
            current_following,
            previous_following
        )

        # -------------------------------------------------
        # Display changes
        # -------------------------------------------------

        print_changes(
            "Followers",
            new_followers,
            lost_followers
        )

        print_changes(
            "Following",
            new_following,
            unfollowed
        )

        print(
            "\n📊 Daily Summary"
        )

        print(
            f"👥 Followers: "
            f"+{len(new_followers)}, "
            f"-{len(lost_followers)}, "
            f"Net: "
            f"{len(new_followers) - len(lost_followers)}"
        )

        print(
            f"➡️ Following: "
            f"+{len(new_following)}, "
            f"-{len(unfollowed)}, "
            f"Net: "
            f"{len(new_following) - len(unfollowed)}"
        )

        # -------------------------------------------------
        # Save
        # -------------------------------------------------

        if args.dry_run:

            print(
                "\n🚫 Dry run: nothing saved "
                "to MongoDB."
            )

        else:

            try:

                save_daily_events(
                    TARGET_USERNAME,
                    new_followers,
                    lost_followers,
                    new_following,
                    unfollowed
                )

                save_current_state(
                    TARGET_USERNAME,
                    current_followers,
                    current_following
                )

                save_successful_run(
                    TARGET_USERNAME
                )

                print(
                    "\n✅ Daily changes "
                    "saved to MongoDB."
                )

                print(
                    "✅ Tracker run marked "
                    "as successful."
                )

            except Exception as e:

                print(
                    "\n❌ Failed to save "
                    "tracking data."
                )

                print(
                    f"Reason: {e}"
                )

                print(
                    "\n⚠️ The run was NOT "
                    "marked as successful."
                )

    finally:

        cleanup_temporary_session(
            session_file,
            temporary_session
        )


# ---------------------------------------------------------
# Entry Point
# ---------------------------------------------------------

if __name__ == "__main__":
    main()