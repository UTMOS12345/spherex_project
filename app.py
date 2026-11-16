"""Old entry point, kept so a server whose systemd unit still says `streamlit run app.py` keeps
working after the app moved to paramost/app.py (the installed unit is a copy that `git pull`
does not update). New setups start the app with `python -m paramost` or `paramost`; see
deploy/spherex.service. Without the launcher the dark theme is not applied."""
import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().parent / "paramost" / "app.py"), run_name="__main__")
