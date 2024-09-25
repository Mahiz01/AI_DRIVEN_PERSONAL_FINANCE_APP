from flask import Flask, render_template, request
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')  # Fix for multithreading issue with plotting
import matplotlib.pyplot as plt
import io
import base64
from scipy.stats import zscore
from sklearn.linear_model import LinearRegression

app = Flask(__name__)

# Function to plot Z-scores and expenses as an image to send to the front end
def plot_z_scores_and_expenses(actual_spending, z_threshold, month):
    fig, ax1 = plt.subplots(figsize=(10, 6))

    # Plot Z-scores
    ax1.bar(actual_spending['Category'], actual_spending['Z-score'], color='blue', alpha=0.6, label='Z-score')
    ax1.axhline(y=z_threshold, color='r', linestyle='--', label='Anomaly Threshold (Z > 2)')
    ax1.axhline(y=-z_threshold, color='r', linestyle='--')
    ax1.set_xlabel('Spending Categories')
    ax1.set_ylabel('Z-score')
    ax1.legend(loc='upper left')

    # Plot Expenses
    ax2 = ax1.twinx()
    ax2.plot(actual_spending['Category'], actual_spending['Actual'], color='green', marker='o', label='Actual Spending')
    ax2.set_ylabel('Spending Amount')
    ax2.legend(loc='upper right')

    plt.title(f'Z-score and Monthly Expenses for Month {month}')
    
    # Save plot to a string buffer
    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    buf.seek(0)
    img = base64.b64encode(buf.read()).decode('utf-8')
    plt.close()
    return img

# Function to plot predicted savings
def plot_predicted_savings(months, actual_savings, future_months, predicted_savings):
    plt.figure(figsize=(10, 6))
    
    # Plot actual savings
    plt.plot(months, actual_savings, color='blue', marker='o', label='Actual Savings')
    
    # Plot predicted savings
    plt.plot(future_months, predicted_savings, color='green', marker='x', linestyle='--', label='Predicted Savings')
    
    plt.title('Savings Prediction for Next 4 Months')
    plt.xlabel('Month')
    plt.ylabel('Savings')
    plt.legend()
    
    # Save plot to a string buffer
    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    buf.seek(0)
    img = base64.b64encode(buf.read()).decode('utf-8')
    plt.close()
    return img

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/calculate-limits', methods=['POST'])
def calculate_limits():
    goal_amount = float(request.form['goal_amount'])
    goal_timeframe_months = int(request.form['goal_timeframe_months'])
    monthly_income = float(request.form['monthly_income'])

    # Initialize results
    limits = []
    essentials_ratio = 0.5
    leisure_ratio = 0.3
    miscellaneous_ratio = 0.2

    # Automatically set limits for each category based on proportions
    monthly_savings_target = goal_amount / goal_timeframe_months
    for month in range(1, goal_timeframe_months + 1):
        remaining_income_for_spending = monthly_income - monthly_savings_target
        categories = {
            'Essentials': essentials_ratio * remaining_income_for_spending,
            'Leisure': leisure_ratio * remaining_income_for_spending,
            'Miscellaneous': miscellaneous_ratio * remaining_income_for_spending
        }
        limits.append(categories)

    return render_template('index.html', limits=limits, goal_amount=goal_amount, 
                           goal_timeframe_months=goal_timeframe_months, monthly_income=monthly_income)

@app.route('/calculate-zscore', methods=['POST'])
def calculate_zscore():
    # Collect form inputs
    goal_amount = float(request.form['goal_amount'])
    goal_timeframe_months = int(request.form['goal_timeframe_months'])
    monthly_income = float(request.form['monthly_income'])

    # Ratios for spending categories
    essentials_ratio = 0.5
    leisure_ratio = 0.3
    miscellaneous_ratio = 0.2

    # Initialize results
    all_results = []
    months = []
    actual_savings = []

    for month in range(1, goal_timeframe_months + 1):
        # Get user input for actual spending from the form
        actual_essentials = float(request.form.get(f'actual_essentials_{month}', 0))
        actual_leisure = float(request.form.get(f'actual_leisure_{month}', 0))
        actual_misc = float(request.form.get(f'actual_misc_{month}', 0))

        # Calculate limits for each category
        remaining_income_for_spending = monthly_income - (goal_amount / goal_timeframe_months)
        categories = {
            'Essentials': essentials_ratio * remaining_income_for_spending,
            'Leisure': leisure_ratio * remaining_income_for_spending,
            'Miscellaneous': miscellaneous_ratio * remaining_income_for_spending
        }

        # Store actual spending and limits in a DataFrame for Z-score calculation
        actual_spending = pd.DataFrame({
            'Category': ['Essentials', 'Leisure', 'Miscellaneous'],
            'Actual': [actual_essentials, actual_leisure, actual_misc],
            'Limit': [categories['Essentials'], categories['Leisure'], categories['Miscellaneous']]
        })

        # Calculate Z-scores to detect anomalies
        actual_spending['Z-score'] = zscore(actual_spending['Actual'] - actual_spending['Limit'], nan_policy='omit')

        # Plot Z-scores and expenses as an image
        z_score_plot = plot_z_scores_and_expenses(actual_spending, 2, month)

        # Calculate total spending and savings
        total_spending = actual_essentials + actual_leisure + actual_misc
        savings = monthly_income - total_spending

        # Store month and savings for later use in prediction
        months.append(month)
        actual_savings.append(savings)

        # Store results for the frontend
        result = {
            'month': month,
            'limits': categories,
            'actuals': {
                'Essentials': actual_essentials,
                'Leisure': actual_leisure,
                'Miscellaneous': actual_misc
            },
            'savings': savings,
            'total_spending': total_spending,
            'z_scores': actual_spending.to_dict(orient='records'),
            'z_score_plot': z_score_plot
        }
        all_results.append(result)

    # Prepare data for savings prediction
    X = np.array(months).reshape(-1, 1)
    y = np.array(actual_savings).reshape(-1)

    # Fit LinearRegression model
    model = LinearRegression()
    model.fit(X, y)

    # Predict savings for the next 4 months
    future_months = np.array([goal_timeframe_months + i for i in range(1, 5)]).reshape(-1, 1)
    predicted_savings = model.predict(future_months)

    # Plot predicted savings
    savings_plot = plot_predicted_savings(months, actual_savings, future_months.flatten(), predicted_savings)

    # Prepare future predictions for the template
    future_predictions = [(month, pred) for month, pred in zip(future_months.flatten(), predicted_savings)]

    total_savings = sum(result['savings'] for result in all_results)
    remaining_savings_needed = goal_amount - total_savings

    return render_template('results.html', results=all_results, total_savings=total_savings,
                           remaining_savings_needed=remaining_savings_needed, 
                           savings_plot=savings_plot, future_predictions=future_predictions)

if __name__ == '__main__':
    app.run(debug=True)
