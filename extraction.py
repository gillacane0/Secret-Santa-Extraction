"""Secret Santa: manage the group, run the draw and email everyone their match."""

import datetime
import smtplib
import tkinter as tk
from contextlib import contextmanager
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from secret_santa.draw import ImpossibleDrawError
from secret_santa.group import Group, Participant, load_group, save_group
from secret_santa.mailer import MailConfigError, SmtpSettings, send_draw, send_test_email

GROUPS_DIR = Path(__file__).resolve().parent / "groups"
FILE_TYPES = [("Secret Santa group", "*.json")]


class ParticipantRow:
    """The fields for one participant in the table."""

    def __init__(self, parent: ttk.Frame, on_remove):
        self.name = ttk.Entry(parent, width=22)
        self.email = ttk.Entry(parent, width=32)
        self.exclude = ttk.Entry(parent, width=44)
        self.remove = ttk.Button(parent, text="✕", width=3, command=lambda: on_remove(self))
        self.widgets = (self.name, self.email, self.exclude, self.remove)

    def place(self, row: int) -> None:
        for column, widget in enumerate(self.widgets):
            widget.grid(row=row, column=column, padx=4, pady=3, sticky="ew")

    def destroy(self) -> None:
        for widget in self.widgets:
            widget.destroy()

    def get(self) -> Participant:
        return Participant(self.name.get(), self.email.get(), self.exclude.get().split(","))

    def set(self, participant: Participant) -> None:
        for entry, value in (
            (self.name, participant.name),
            (self.email, participant.email),
            (self.exclude, ", ".join(participant.exclude)),
        ):
            entry.delete(0, tk.END)
            entry.insert(0, value)

    def is_blank(self) -> bool:
        return not any(entry.get().strip() for entry in (self.name, self.email, self.exclude))


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.group = Group()
        self.path: Path | None = None
        self.rows: list[ParticipantRow] = []
        self.buttons: list[ttk.Button] = []
        self.is_busy = False

        self.budget = tk.StringVar()
        self.history_years = tk.StringVar(value=str(self.group.history_years))
        self.single_chain = tk.BooleanVar()
        self.status = tk.StringVar()

        self._build()
        self.show(self.group)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    # ----- Layout -----

    def _build(self) -> None:
        main = ttk.Frame(self.root, padding=12)
        main.pack(fill=tk.BOTH, expand=True)

        toolbar = ttk.Frame(main)
        toolbar.pack(fill=tk.X)
        for text, command in (
            ("New", self.new_group),
            ("Open…", self.open_group),
            ("Save", self.save),
            ("Save as…", self.save_as),
        ):
            self._button(toolbar, text, command).pack(side=tk.LEFT, padx=(0, 4))

        settings = ttk.LabelFrame(main, text="Settings", padding=8)
        settings.pack(fill=tk.X, pady=10)
        ttk.Label(settings, text="Budget").pack(side=tk.LEFT)
        ttk.Entry(settings, textvariable=self.budget, width=14).pack(side=tk.LEFT, padx=(4, 24))
        ttk.Label(settings, text="Avoid the pairings of the last").pack(side=tk.LEFT)
        ttk.Spinbox(settings, from_=0, to=10, width=4, textvariable=self.history_years).pack(side=tk.LEFT, padx=4)
        ttk.Label(settings, text="years").pack(side=tk.LEFT, padx=(0, 24))
        ttk.Checkbutton(
            settings, text="Single chain (A → B → C → … → A)", variable=self.single_chain
        ).pack(side=tk.LEFT)

        people = ttk.LabelFrame(main, text="Participants", padding=8)
        people.pack(fill=tk.BOTH, expand=True)
        # A small requested height, so the table only takes the space left and never pushes the buttons out.
        canvas = tk.Canvas(
            people, height=100, highlightthickness=0, background=ttk.Style().lookup("TFrame", "background")
        )
        scrollbar = ttk.Scrollbar(people, orient=tk.VERTICAL, command=canvas.yview)
        self.table = ttk.Frame(canvas)
        self.table.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.table, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(-e.delta // 120, "units"))
        for column, title in enumerate(("Name", "Email", "Never give to (comma-separated)")):
            ttk.Label(self.table, text=title, font="TkHeadingFont").grid(row=0, column=column, padx=4, sticky="w")
        self._button(main, "+ Add participant", self.add_row).pack(anchor="w", pady=(6, 0))

        actions = ttk.Frame(main)
        actions.pack(fill=tk.X, pady=(10, 0))
        ttk.Label(actions, textvariable=self.status, foreground="gray").pack(side=tk.LEFT)
        self._button(actions, "Draw and send emails", self.draw_and_send).pack(side=tk.RIGHT)
        self._button(actions, "Test run", self.test_run).pack(side=tk.RIGHT, padx=6)

    def _button(self, parent, text: str, command) -> ttk.Button:
        button = ttk.Button(parent, text=text, command=command)
        self.buttons.append(button)
        return button

    def add_row(self, participant: Participant | None = None) -> None:
        row = ParticipantRow(self.table, self.remove_row)
        if participant:
            row.set(participant)
        self.rows.append(row)
        row.place(len(self.rows))

    def remove_row(self, row: ParticipantRow) -> None:
        row.destroy()
        self.rows.remove(row)
        for i, other in enumerate(self.rows, start=1):
            other.place(i)

    # ----- Moving data between the window and the group -----

    def show(self, group: Group) -> None:
        self.group = group
        for row in self.rows:
            row.destroy()
        self.rows.clear()
        for participant in group.participants:
            self.add_row(participant)
        for _ in range(3 - len(group.participants)):
            self.add_row()
        self.budget.set(group.budget)
        self.history_years.set(str(group.history_years))
        self.single_chain.set(group.single_chain)
        self.root.title(f"Secret Santa — {self.path.name if self.path else 'new group'}")

    def collect(self) -> Group | None:
        """Copy the window's contents into the group; None (after saying why) if a field is invalid."""
        try:
            history_years = int(self.history_years.get())
        except ValueError:
            messagebox.showerror("Invalid value", "The years of pairings to avoid must be a whole number.")
            return None
        self.group.participants = [row.get() for row in self.rows if not row.is_blank()]
        self.group.budget = self.budget.get().strip()
        self.group.history_years = history_years
        self.group.single_chain = self.single_chain.get()
        return self.group

    # ----- Files -----

    def new_group(self) -> None:
        if any(not row.is_blank() for row in self.rows) and not messagebox.askyesno(
            "New group", "Clear the current group? Unsaved changes will be lost."
        ):
            return
        self.path = None
        self.show(Group())

    def open_group(self) -> None:
        GROUPS_DIR.mkdir(exist_ok=True)
        path = filedialog.askopenfilename(initialdir=GROUPS_DIR, filetypes=FILE_TYPES)
        if not path:
            return
        try:
            group = load_group(Path(path))
        except (OSError, ValueError, TypeError, AttributeError) as error:
            messagebox.showerror("Can't open the file", f"This doesn't look like a group file:\n{error}")
            return
        self.path = Path(path)
        self.show(group)

    def save(self) -> bool:
        if self.path is None:
            return self.save_as()
        group = self.collect()
        if group is None:
            return False
        try:
            save_group(group, self.path)
        except OSError as error:
            messagebox.showerror("Can't save", str(error))
            return False
        self.status.set(f"Saved {self.path.name}")
        return True

    def save_as(self) -> bool:
        GROUPS_DIR.mkdir(exist_ok=True)
        path = filedialog.asksaveasfilename(initialdir=GROUPS_DIR, defaultextension=".json", filetypes=FILE_TYPES)
        if not path:
            return False
        self.path = Path(path)
        self.root.title(f"Secret Santa — {self.path.name}")
        return self.save()

    # ----- Draw -----

    def test_run(self) -> None:
        prepared = self._prepare()
        if prepared is None:
            return
        group, settings = prepared
        try:
            group.make_draw(datetime.date.today().year)
        except ImpossibleDrawError as error:
            messagebox.showerror("The draw isn't possible", str(error))
            return
        try:
            with self.busy("Sending a test email…"):
                send_test_email(settings, group)
        except (smtplib.SMTPException, OSError) as error:
            self._show_mail_error(error)
            return
        messagebox.showinfo(
            "Test run",
            f"All good! The draw is possible and a sample email was sent to {settings.user}.\n\n"
            "Nothing was drawn for real and nothing was saved.",
        )

    def draw_and_send(self) -> None:
        prepared = self._prepare()
        if prepared is None:
            return
        group, settings = prepared
        year = datetime.date.today().year
        try:
            pairs = group.make_draw(year)
        except ImpossibleDrawError as error:
            messagebox.showerror("The draw isn't possible", str(error))
            return
        # The history is saved in the group file, so the group needs one.
        if self.path is None and not self.save_as():
            return
        question = f"Draw and email all {len(pairs)} participants? This can't be undone."
        if str(year) in group.history.draws:
            question += f"\n\nIt replaces the {year} draw already in the history."
        if not messagebox.askyesno("Ready?", question):
            return

        failed = self._send(settings, group, pairs)
        if failed is None:  # couldn't connect: nothing was sent
            return
        while failed and messagebox.askretrycancel("Some emails weren't sent", "Couldn't email: " + ", ".join(failed)):
            retried = self._send(settings, group, {giver: pairs[giver] for giver in failed})
            if retried is not None:
                failed = retried
        if len(failed) == len(pairs):
            messagebox.showwarning("Nothing sent", "No email was sent, so the draw was discarded. You can try again.")
            return

        group.history.record(year, pairs)
        try:
            save_group(group, self.path)
        except OSError as error:
            messagebox.showerror("Can't save the history", str(error))
        if not failed:
            messagebox.showinfo("Done!", f"All {len(pairs)} emails were sent. Merry Christmas!")
        elif messagebox.askyesno(
            "Tell them yourself?",
            "Do you want to see who these people got, so you can tell them yourself?\n\n"
            "It will spoil the surprise for you.",
        ):
            messagebox.showinfo("Unsent matches", "\n".join(f"{giver} → {pairs[giver]}" for giver in failed))

    def _prepare(self) -> tuple[Group, SmtpSettings] | None:
        """Check the group and the email settings, showing what's wrong if anything."""
        group = self.collect()
        if group is None:
            return None
        errors = group.validate()
        if errors:
            messagebox.showerror("Please fix these first", "\n".join(f"• {error}" for error in errors))
            return None
        try:
            settings = SmtpSettings.from_env()
        except MailConfigError as error:
            messagebox.showerror("Email not set up", str(error))
            return None
        return group, settings

    def _send(self, settings: SmtpSettings, group: Group, pairs: dict[str, str]) -> list[str] | None:
        """Send the emails. Returns who didn't get theirs, or None if the connection failed."""
        try:
            with self.busy("Connecting to the email server…"):
                return send_draw(settings, group, pairs, on_progress=self._show_progress)
        except (smtplib.SMTPException, OSError) as error:
            self._show_mail_error(error)
            return None

    def _show_progress(self, done: int, total: int) -> None:
        self.status.set(f"Sending email {done} of {total}…")
        self.root.update()

    def _show_mail_error(self, error: Exception) -> None:
        if isinstance(error, smtplib.SMTPAuthenticationError):
            message = (
                "Login failed. Check SMTP_USER and SMTP_PASSWORD in .env.\n\n"
                "For Gmail you need an app password, not your normal password."
            )
        else:
            message = f"Couldn't talk to the email server:\n{error}"
        messagebox.showerror("Email error", message)

    @contextmanager
    def busy(self, message: str):
        """Show `message` and block the buttons while something slow happens."""
        self.is_busy = True
        self.status.set(message)
        self.root.config(cursor="watch")
        for button in self.buttons:
            button.state(["disabled"])
        self.root.update()
        try:
            yield
        finally:
            self.is_busy = False
            self.status.set("")
            self.root.config(cursor="")
            for button in self.buttons:
                button.state(["!disabled"])

    def close(self) -> None:
        if not self.is_busy:
            self.root.destroy()


def main() -> None:
    root = tk.Tk()
    root.geometry("960x620")
    root.minsize(760, 420)
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
