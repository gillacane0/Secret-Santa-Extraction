import tkinter as tk
import numpy as np
from tkinter import messagebox
import smtplib
import string
from tokenize import String
from dataclasses import dataclass
import random


# Function to create input fields based on the number of participants
def create_input_fields():
    try:
        num_participants = int(entry_num_participants.get())  # Get the number of participants
        if num_participants <= 0:
            raise ValueError  # Ensure the number is positive
    except ValueError:
        messagebox.showerror("Error", "Please enter a valid number of participants.")
        return

    # Clear the window from any previous input
    for widget in frame_input.winfo_children():
        widget.destroy()

    # Create input fields for each person (name, mail address, list of names)
    for i in range(num_participants):
        label_name = tk.Label(frame_input, text=f"Name of participant {i + 1}:")
        label_name.grid(row=i, column=0, padx=5, pady=5)
        entry_name = tk.Entry(frame_input)
        entry_name.grid(row=i, column=1, padx=5, pady=5)

        label_mailaddress = tk.Label(frame_input, text=f"Mail address of participant {i + 1}:")
        label_mailaddress.grid(row=i, column=2, padx=5, pady=5)
        entry_mailaddress = tk.Entry(frame_input)
        entry_mailaddress.grid(row=i, column=3, padx=5, pady=5)

        label_name_list = tk.Label(frame_input, text=f"List of excluded for participant {i + 1} (comma-separated):")
        label_name_list.grid(row=i, column=4, padx=5, pady=5)
        entry_name_list = tk.Entry(frame_input)
        entry_name_list.grid(row=i, column=5, padx=5, pady=5)

        # Save the input fields to retrieve them later
        participant_fields.append((entry_name, entry_mailaddress, entry_name_list))

    # Add a button to finalize and display the data
    button_confirm = tk.Button(frame_input, text="Confirm", command=save_data_and_close)
    button_confirm.grid(row=num_participants, column=0, columnspan=6, pady=10)


# Function to save the entered data, close the window, and execute the block of instructions
def save_data_and_close():
    participant_data = []
    for i, (entry_name, entry_mailaddress, entry_name_list) in enumerate(participant_fields):
        name = entry_name.get()
        address = entry_mailaddress.get()
        name_list = entry_name_list.get().split(',')  # Split the list of names by comma

        # Remove any extra spaces around the names in the list
        name_list = [n.strip() for n in name_list if n.strip()]

        if name and address and name_list:
            participant_data.append((name, address, name_list))
        else:
            messagebox.showerror("Error",
                                 f"Please enter name, mail address, and a valid list of names for participant {i + 1}.")
            return


    # Close the window
    root.destroy()


    extraction_algorithm(participant_data)


def extraction_algorithm(participant_data):


   email = ""  # your email used for sending the results of each of your friend
   subject = ("SECRET SANTA EXTRACTION: ")
   #server = smtplib.SMTP("smtp.gmail.com", 587)
   #server.starttls()
   #server.login(email,"")  # here you must put the alternative access password of the mail, CAUTION!! not the actual password, see readme

   groupExtracted = []

   #im creating an auxilary data structure and add each person to his list of excluded
   for val in participant_data:
       groupExtracted.append(val[0])
       val[2].append(val[0])


   for val in participant_data:
       while True:
           extracted = random.choice(groupExtracted)
           if not (extracted in val[2]):
               groupExtracted.remove(extracted)
               break

       message = (val[0], "you have to make the gift to ", extracted)
       text = f"Subject: {subject}\n\n{message}"
       #server.sendmail(email, val[1], text)


# Create the main window
root = tk.Tk()
root.title("Participants Registration")
root.geometry("1200x600")

# Frame for the first question
frame_num_participants = tk.Frame(root)
frame_num_participants.pack(pady=20)

label_num_participants = tk.Label(frame_num_participants, text="How many people are participating in the game?")
label_num_participants.pack(side=tk.LEFT, padx=10)

entry_num_participants = tk.Entry(frame_num_participants)
entry_num_participants.pack(side=tk.LEFT, padx=10)

button_num_participants = tk.Button(frame_num_participants, text="Confirm", command=create_input_fields)
button_num_participants.pack(side=tk.LEFT, padx=10)

# Frame where the dynamic input fields will be inserted
frame_input = tk.Frame(root)
frame_input.pack(pady=20)

# List to save tuples of input fields (name, address, list of names)
participant_fields = []

# Start the main loop
root.mainloop()