In order to work, this program needs to use your email account. Inside the code, you will need to find the following part and remove the comments:

#server = smtplib.SMTP("smtp.gmail.com", 587)
#server.starttls()
#server.login(email, "")  # here you must put the alternative access password of the mail, CAUTION!! not the actual password, see readme


In #server.login(email, ""), inside the parentheses, you need to enter a password that is not the actual password for the account, but an alphanumeric code provided by Google to access from other devices. You can find this code in your Google account. Note: Two-factor authentication must be enabled.
You should search under "Signing in to Google > App password"

Remove also the comment from the instruction below, and the program will be ready:

#server.sendmail(email, val[1], text)


