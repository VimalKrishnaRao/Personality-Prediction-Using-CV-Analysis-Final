from flask import Flask, flash,render_template,url_for,redirect,request,jsonify,send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin,login_user,LoginManager,login_required,logout_user,current_user
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import InputRequired,ValidationError,Length,Email
from flask_bcrypt import Bcrypt

from datetime import datetime
import os
import pandas as pd
import csv
from ai_prediction import chat
from resume_extraction import (
    extract_text_based_on_file,
    extract_name,
    extract_contact_info,
    extract_education,
    extract_work_experience,
    extract_skills,
)


app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SECRET_KEY'] = 'thisisasecretkey'
app.config['STATIC_FOLDER'] = 'static'
UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
db = SQLAlchemy(app)
bcrypt = Bcrypt(app)


login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view= "login"


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


class User(db.Model,UserMixin):
    id = db.Column(db.Integer, primary_key = True, autoincrement = True)
    username = db.Column(db.String(20),nullable = False,unique = True)
    password = db.Column(db.String(80),nullable = False)
    first_name = db.Column(db.String(30), nullable=False)
    last_name = db.Column(db.String(30), nullable=False)


class SignupForm(FlaskForm):
    username = StringField(validators = [InputRequired(),Length(
    min=4,max=20)],render_kw={"placeholder": "Username"})

    password = PasswordField(validators=[InputRequired(),Length(
    min=4,max=20)],render_kw={"placeholder": "Password"})

    first_name = StringField(validators=[InputRequired(), Length(
    min=2, max=30)],render_kw={"placeholder": "First name"})
    
    last_name = StringField(validators=[InputRequired(), Length(
    min=2, max=30)],render_kw={"placeholder": "Last name"})

    submit = SubmitField("SignUp")
    
    def validate_username(self,username):
        ext_user_username = User.query.filter_by(
            username = username.data).first()
        if ext_user_username:
            raise ValidationError("This username already exist! Choose a different one")



class LoginForm(FlaskForm):
    username = StringField(validators = [InputRequired(),Length(
    min=4,max=20)],render_kw={"placeholder": "Username"})

    password = PasswordField(validators=[InputRequired(),Length(
    min=4,max=20)],render_kw={"placeholder": "Password"})

    submit = SubmitField("LogIn")

@app.route('/')
def home():
    #return "<h1>welcome</h1>"
    return render_template('home.html')



@app.route('/login', methods=['GET','POST'])
def login():
    form = LoginForm()

    if form.validate_on_submit():
        user = User.query.filter_by(username = form.username.data).first()
        if user:
            if bcrypt.check_password_hash(user.password,form.password.data):
                login_user(user)
            else:
                flash('Invalid username or password', 'error')
        return redirect(url_for('dashboard'))

    return render_template('login.html',form = form)


@app.route('/logout',methods = ['GET','POST'])
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))



@app.route('/signup', methods=['GET','POST'])
def signup():
    form = SignupForm()

    if form.validate_on_submit():
        hashed_password = bcrypt.generate_password_hash(form.password.data).decode('utf-8') 
        new_user = User(username = form.username.data,password = hashed_password,first_name= form.first_name.data, last_name=form.last_name.data)

        db.session.add(new_user)
        db.session.commit()

        return redirect(url_for('login'))

    return render_template('signup.html',form = form)


@app.route('/dashboard',methods = ['GET','POST'])
@login_required
def dashboard():
    return render_template('dashboard.html')

from prediction import assign_personality_traits
@app.route('/analyze', methods=['POST'])
def analyze_resume():
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file part in the request'}), 400
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No selected file'}), 400
        if file:
            filename = file.filename
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)

            # Extract text from uploaded resume
            text = extract_text_based_on_file(file_path)

            # Generate a unique row_number using the current timestamp
            row_number = datetime.now().strftime("%Y%m%d%H%M%S")

            # Extract information from the text
            name = extract_name(filename, row_number)
            contact_info = extract_contact_info(text)
            education = extract_education(text)
            work_experience = extract_work_experience(text)
            skills = extract_skills(text)

            # Save the extracted details to a CSV file
            extracted_details = {
                'Filename': filename,
                'Name': name,
                'Contact Information': contact_info,
                'Education': education,
                'Work Experience': work_experience,
                'Skills': skills,
            }
            save_to_csv(extracted_details, 'extracted_details.csv')

            # Get the personality traits
            personality_traits = assign_personality_traits(extracted_details)

            # Add the personality traits to the extracted details
            extracted_details.update(personality_traits)
            # Generate a response from the AI model
            query = "describe a candidate's personality if his traits are: " + ', '.join(
                f"{k}: {v}" for k, v in personality_traits.items())
            response = chat(query)

            # Render the 'result.html' template with extracted details and AI response passed as variables
            return render_template('result.html',
                                   name=name,
                                   contact_info=contact_info,
                                   education=education,
                                   work_experience=work_experience,
                                   skills=skills,
                                   personality_traits=personality_traits,
                                   response=response)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/history', methods=['GET'])
def get_history():
    try:
        data = pd.read_csv('extracted_details.csv')
        return data.to_json(orient='records')
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/clear_history', methods=['POST'])
def clear_history():
    try:
        open('extracted_details.csv', 'w').close()  # This will clear the file
        return jsonify({'success': 'History cleared'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/export_data', methods=['GET'])
def export_data():
    try:
        return send_file('extracted_details.csv', as_attachment=True)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def save_to_csv(data, filename):
    try:
        # Check if file exists
        file_exists = os.path.isfile(filename)

        with open(filename, mode='a', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            # Write header only if file didn't exist
            if not file_exists:
                writer.writerow(data.keys())
            # Write data row
            writer.writerow(data.values())
    except Exception as e:
        print(f"Error occurred while saving to CSV: {e}")


if __name__ == "__main__":
    app.run(debug=True)

