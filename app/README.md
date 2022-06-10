
# How do I run this locally?

You can run this locally, setting up the database the first time is the hardest part:

1. First, if you haven't already, install MongoDB: [https://docs.mongodb.com/manual/administration/install-community/](https://docs.mongodb.com/manual/administration/install-community/)
2. Start the server / MongoDB shell by running `mongod` on the command line
    > **_NOTE:_**  MongoDB actually doesn't create the database/document until an entry is inputted. So you don't have to do anything in the shell, although you could run `show dbs` later to verify the database was created.
3. Create a .env file with the local `MONGODB_URI` in it along with the PORT you want to run the flights on `8080`, e.g.:
    ```
    touch .env
    echo "MONGODB_URI=localhost:27017" > .env
    echo "PORT=8080" >> .env
    echo "LOCAL=True" >> .env
    ```
4. Install the python requirements (best to do in a virtual environment):
    ```
    pip install -r ../requirements.txt
    ```
5. Run main.py (`python main.py` on the command line)
6. Open up [0.0.0.0:8000](0.0.0.0:8080) in your web browser