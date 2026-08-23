# Typer — bir tuşa bas, konuş, yazı imlecin nerede ise oraya düşsün.
# Copyright (C) 2026 Bertan Taskiran
#
# Derived from backtalk (https://github.com/jaredrhod/backtalk),
# Copyright (C) 2026 Jared Rhodenizer.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Typer — push-to-dictate, and nothing else.

Press the key, talk, press again. The words are transcribed locally and
pasted at the cursor, in whatever application has focus.

Everything here runs on this machine: the speech model is faster-whisper
running in-process, and no audio, text or telemetry leaves the computer.
There is no account, no API key and no network call in the hot path.
"""

__version__ = "1.0.0"
