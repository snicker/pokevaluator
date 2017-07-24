this is spaghetti.

copy accounts.json.example to accounts.json and edit
run pokebotflask.py, default port is 9999. I recommend using nginx and wsgi so you can control that

probably run this somewhere secure since your account creds are in plaintext with an SSL cert, and maybe protect it with basic auth because you can wipe out your pokemon with this.