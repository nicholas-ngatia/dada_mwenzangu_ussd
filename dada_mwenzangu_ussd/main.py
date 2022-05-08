import redis
import ast
from pymongo import MongoClient
from flask import Flask, request

app = Flask(__name__)
r = redis.StrictRedis("localhost", 6379, charset="utf-8", decode_responses=True)
m = MongoClient()


def county_check(ussd_string):
    if ussd_string == "1":
        county = "Nairobi"
    elif ussd_string == "2":
        county = "Kisumu"
    elif ussd_string == "3":
        county = "Mombasa"
    else:
        county = "Invalid"
    return county


def id_validate(ussd_string):
    try:
        ussd_string = int(ussd_string)
        if len(str(ussd_string)) < 5 or len(str(ussd_string)) > 8:
            return False
        else:
            return True
    except ValueError:
        return False


@app.post("/ussd")
def ussd():
    try:
        session_id = request.values.get("sessionId", None)
        service_code = request.values.get("serviceCode", None)
        phone_number = request.values.get("phoneNumber", None)
        ussd_string = str(request.values.get("text", "default"))
        ussd_string = ussd_string.split("*")[-1]
        session = r.hgetall(session_id)
        db = m["customer-details"]
        current_screen = "main_menu"
        if session:
            current_screen = session["current_screen"]
        if ussd_string == "0":
            current_screen = session["previous_screen"]
            ussd_string = session["response"]
        if ussd_string == "00":
            current_screen = "main_menu"
        if current_screen == "main_menu":
            print(current_screen)
            customer_data = r.hgetall(phone_number)
            print(customer_data)
            print(db["client_details"].find_one({"client_number": phone_number}))
            if not customer_data and not db["client_details"].find_one(
                {"client_number": phone_number}
            ):
                response = "CON Welcome to Dada Mwenzangu, where you can help women in need. Kindly enter your name to proceed."
                current_screen = "register_start"
            else:
                customer_data = ast.literal_eval(str(customer_data))
                response = "CON Welcome back to Dada Mwenzangu.\n1. Request for help\n2. Offer help"
                current_screen = "help_menu"
            r.hmset(
                session_id,
                {
                    "customer_data": str(customer_data),
                    "current_screen": current_screen,
                    "previous_screen": "main_menu",
                    "response": response,
                },
            )

        elif current_screen == "register_start":
            response = f"CON Hello {ussd_string}. Kindly select your region next.\n1. Nairobi\n2. Kisumu\n3. Mombasa"
            r.hmset(
                phone_number,
                {"customer_name": ussd_string},
            )
            r.hmset(
                session_id,
                {
                    "customer_name": ussd_string,
                    "current_screen": "register_location",
                    "previous_screen": current_screen,
                    "response": response,
                },
            )
        elif current_screen == "register_location":
            county = county_check(ussd_string)
            if county == "Invalid":
                response = f"CON Invalid choice selected. Please try again.\n{session['response']}"
            else:
                response = "CON Please enter your id number to complete the process"
            r.hmset(
                phone_number,
                {"county": county},
            )
            r.hmset(
                session_id,
                {
                    "county": county,
                    "county_id": ussd_string,
                    "current_screen": "register_id",
                    "previous_screen": current_screen,
                    "response": response,
                },
            )
        elif current_screen == "register_id":
            validate = id_validate(ussd_string)
            if validate:
                customer_data = ast.literal_eval(str(session))
                response = f"CON Kindly confirm details\nName = {customer_data['customer_name']}\nCounty = {customer_data['county']}\nId number = {ussd_string}\n1. Confirm"
                next_screen = "register_confirm"
            else:
                response = "CON Invalid id number entered, please try again"
                next_screen = "register_id"
            r.hmset(
                session_id,
                {
                    "id_number": ussd_string,
                    "current_screen": next_screen,
                    "previous_screen": "main_menu",
                    "response": response,
                },
            )
        elif current_screen == "register_confirm":
            customer_data = ast.literal_eval(str(session))
            response = "CON Thank you for registering for Dada Mwenzangu.\n1. Offer help\n2. Request help"
            r.hmset(
                session_id,
                {
                    "current_screen": "help_menu",
                    "previous_screen": current_screen,
                    "response": response,
                },
            )
            r.hmset(
                phone_number,
                {"registered": "1"},
            )
            client_table = db["client_details"]
            client_table.insert_one(
                {
                    "client_name": customer_data["customer_name"],
                    "client_location_id": customer_data["county_id"],
                    "client_id": customer_data["id_number"],
                    "phone_number": phone_number,
                    "used": 0,
                }
            )
        elif current_screen == "help_menu":
            if ussd_string == "1":
                client_table = db["client_details"]
                requester_details = client_table.find_one(
                    {"phone_number": phone_number}
                )
                selection = client_table.find_one(
                    {
                        "used": 0,
                        "client_location_id": requester_details["client_location_id"],
                        "phone_number": {"$ne": phone_number},
                    }
                )
                if selection:
                    response = f"CON The following person is in the same location as you: 0{selection['phone_number'][3:]}. Would you like to contact them?"
                    next_screen = "help_continue"
                else:
                    response = "CON We unfortunately do not have a requested person in the area. Would you like to check a location slightly further away?\n1. Confirm"
                    next_screen = "next_location"
                r.hmset(
                    session_id,
                    {
                        "current_screen": next_screen,
                        "previous_screen": current_screen,
                        "response": response,
                        "selection": selection[phone_number],
                    },
                )
            elif ussd_string == "2":
                # TO DO
                response = "END Menu currently in progress. Please check back later"
                r.hmset(
                    session_id,
                    {
                        "current_screen": "main_menu",
                        "previous_screen": "main_menu",
                        "response": response,
                    },
                )
        elif current_screen == "help_continue":
            customer_data = ast.literal_eval(str(session))
            response = "END We are currently sending you an SMS with their details to be able to contact them. Please wait."
            client_table = db["client_details"]
            client_table.update_one(
                {"phone_number": phone_number}, {"set": {"used": 1}}
            )
        elif current_screen == "next_location":
            requester_details = client_table.find_one({"phone_number": phone_number})
            second_choice = db["closest_locations"].find_one(
                {"location": requester_details["client_location_id"]}
            )
            selection = client_table.find_one(
                {
                    "used": 0,
                    "client_location_id": second_choice["next_closest_location"],
                    "phone_number": {"$ne": phone_number},
                }
            )
            if selection:
                response = f"CON The following person is in the same location as you: 0{selection['phone_number'][3:]}. Would you like to contact them?\n1. Confirm"
                next_screen = "help_continue"
            else:
                response = "CON We unfortunately do not have a requested person in the area. Kindly check back later to see more options"
                next_screen = "main_menu"
            r.hmset(
                session_id,
                {
                    "current_screen": next_screen,
                    "previous_screen": current_screen,
                    "response": response,
                },
            )

        return response
    except Exception as e:
        print(f"Shit's fucking {e}")
        return "END An error occurred, please try again later"


if __name__ == "__main__":
    app.run(debug=True)
