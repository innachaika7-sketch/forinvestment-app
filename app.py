from flask import Flask, render_template, request, redirect, url_for, flash, send_file
from datetime import datetime, date
import database as db
import io
import pandas as pd
import os

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'

@app.template_filter('format_number')
def format_number(value):
    if value is None:
        return ''
    try:
        if isinstance(value, (int, float)):
            return '{:,.2f}'.format(value).replace(',', ' ')
    except:
        pass
    return str(value)

@app.template_filter('format_money')
def format_money(value):
    if value is None:
        return ''
    try:
        num = float(value)
        sign = ''
        if num < 0:
            sign = '-'
            num = abs(num)
        if num >= 1_000_000:
            return f"{sign}{num/1_000_000:.2f} м"
        elif num >= 1_000:
            return f"{sign}{num/1_000:.2f} т"
        else:
            return f"{sign}{num:.2f}"
    except:
        return str(value)

@app.template_filter('date_format')
def date_format(value):
    if not value:
        return ''
    try:
        dt = datetime.strptime(value, '%Y-%m-%d')
        return dt.strftime('%d.%m.%Y')
    except:
        return value

@app.route('/')
def dashboard():
    sort_by = request.args.get('sort', 'invested')
    order = request.args.get('order', 'desc')

    projects_agg = db.get_project_aggregates()
    total_in = sum(p['total_in'] for p in projects_agg)
    total_out = sum(p['total_out'] for p in projects_agg)
    profit = total_in - total_out
    roi_portfolio = (profit / total_out * 100) if total_out > 0 else 0

    payments = db.get_payments()
    today = date.today()
    upcoming = None
    overdue_summary = {}
    for p in payments:
        try:
            p_date = datetime.strptime(p['date'], '%Y-%m-%d').date()
        except:
            continue
        if p_date >= today:
            if upcoming is None or p_date < datetime.strptime(upcoming['date'], '%Y-%m-%d').date():
                upcoming = {'date': p['date'], 'amount': p['amount'], 'project': p['project_name']}
        else:
            key = p['project_name'] or 'Без проекта'
            if key not in overdue_summary:
                overdue_summary[key] = {'total': 0, 'oldest': p['date']}
            overdue_summary[key]['total'] += p['amount']
            if p['date'] < overdue_summary[key]['oldest']:
                overdue_summary[key]['oldest'] = p['date']

    projects_with_roi = []
    for p in projects_agg:
        invested = p['total_out']
        returned = p['total_in']
        net = returned - invested
        roi = (net / invested * 100) if invested > 0 else 0
        projects_with_roi.append({
            'name': p['name'],
            'invested': invested,
            'returned': returned,
            'net': net,
            'roi': roi,
            'type': p.get('type', 'Доля'),
            'share_percent': p.get('share_percent'),
            'investment_amount': p.get('investment_amount'),
            'contract_number': p.get('contract_number')
        })

    if sort_by == 'invested':
        projects_with_roi.sort(key=lambda x: x['invested'], reverse=(order == 'desc'))
    elif sort_by == 'returned':
        projects_with_roi.sort(key=lambda x: x['returned'], reverse=(order == 'desc'))
    elif sort_by == 'net':
        projects_with_roi.sort(key=lambda x: x['net'], reverse=(order == 'desc'))
    elif sort_by == 'roi':
        projects_with_roi.sort(key=lambda x: x['roi'], reverse=(order == 'desc'))
    else:
        projects_with_roi.sort(key=lambda x: x['invested'], reverse=(order == 'desc'))

    return render_template('dashboard.html',
                           projects=projects_with_roi,
                           total_in=total_in,
                           total_out=total_out,
                           profit=profit,
                           roi_portfolio=roi_portfolio,
                           upcoming=upcoming,
                           overdue_summary=overdue_summary,
                           sort_by=sort_by,
                           order=order)

@app.route('/calculator_root')
def calculator_root():
    return render_template('calculator_root.html')

@app.route('/operations_root')
def operations_root():
    return render_template('operations_root.html')

@app.route('/projects_root')
def projects_root():
    return render_template('projects_root.html')

# -------------------- КАЛЬКУЛЯТОР --------------------
@app.route('/calculator', methods=['GET', 'POST'])
def calculator():
    default_investment = 1000000
    default_method = 'Доля'
    default_mode = 'sum'
    default_expected_return = 1200000
    default_dividends = 0
    default_sell_share = 'false'
    default_exit_price = 0
    default_term_months_loan = 12
    default_annual_rate = 15
    default_deposit_rate = 10
    default_discount_enabled = False
    default_discount_rate = 12
    default_term_months_common = 12

    if request.method == 'POST':
        investment = float(request.form.get('investment', default_investment))
        method = request.form.get('method', default_method)
        mode = request.form.get('mode', default_mode)
        expected_return = float(request.form.get('expected_return', default_expected_return)) if mode == 'sum' else 0
        dividends = float(request.form.get('dividends', default_dividends)) if mode == 'share' else 0
        sell_share = request.form.get('sell_share', default_sell_share)
        exit_price = float(request.form.get('exit_price', default_exit_price)) if sell_share == 'true' else 0
        term_months_loan = int(request.form.get('term_months', default_term_months_loan)) if mode == 'loan' else default_term_months_loan
        annual_rate = float(request.form.get('annual_rate', default_annual_rate)) if mode == 'loan' else 0
        deposit_rate = float(request.form.get('deposit_rate', default_deposit_rate))
        discount_enabled = request.form.get('discount_enabled') == 'on'
        discount_rate = float(request.form.get('discount_rate', default_discount_rate)) if discount_enabled else 0
        term_months_common = int(request.form.get('term_months', default_term_months_common)) if mode in ('sum', 'share') else default_term_months_common
    else:
        investment = default_investment
        method = default_method
        mode = default_mode
        expected_return = default_expected_return
        dividends = default_dividends
        sell_share = default_sell_share
        exit_price = default_exit_price
        term_months_loan = default_term_months_loan
        annual_rate = default_annual_rate
        deposit_rate = default_deposit_rate
        discount_enabled = default_discount_enabled
        discount_rate = default_discount_rate
        term_months_common = default_term_months_common

    result = None
    error = None

    if request.method == 'POST':
        try:
            term_months = term_months_common if mode in ('sum', 'share') else term_months_loan
            total_return = 0
            cash_flows = []

            if mode == 'sum':
                total_return = expected_return
                cash_flows.append({'months': term_months, 'amount': expected_return})
            elif mode == 'share':
                total_return = dividends + (exit_price if sell_share == 'true' else 0)
                if term_months > 0:
                    cash_flows.append({'months': term_months // 2, 'amount': dividends})
                    if sell_share == 'true':
                        cash_flows.append({'months': term_months, 'amount': exit_price})
            elif mode == 'loan':
                years = term_months / 12
                total_return = investment * (1 + (annual_rate / 100) * years)
                cash_flows.append({'months': term_months, 'amount': total_return})
            else:
                raise ValueError('Неизвестный режим')

            profit = total_return - investment
            roi = (profit / investment * 100) if investment > 0 else 0

            annual_return = None
            if term_months > 0 and investment > 0:
                years = term_months / 12
                annual_return = (pow(total_return / investment, 1 / years) - 1) * 100 if total_return > 0 else 0

            def calculate_irr(investment, cash_flows):
                if not cash_flows or investment <= 0:
                    return None
                # Проверяем, есть ли положительные потоки
                if sum(cf['amount'] for cf in cash_flows) <= 0:
                    return None
                periods = [{'years': cf['months'] / 12, 'amount': cf['amount']} for cf in cash_flows]
                guess = 0.1
                tolerance = 1e-6
                max_iter = 100
                for _ in range(max_iter):
                    npv = -investment
                    dnpv = 0
                    for p in periods:
                        if p['years'] == 0:
                            npv += p['amount']
                        else:
                            npv += p['amount'] / pow(1 + guess, p['years'])
                            dnpv += -p['years'] * p['amount'] / pow(1 + guess, p['years'] + 1)
                    if dnpv == 0:
                        break
                    new_guess = guess - npv / dnpv
                    if abs(new_guess - guess) < tolerance:
                        return new_guess * 100
                    guess = new_guess
                    if guess < -0.99:
                        guess = -0.9
                return None

            irr = calculate_irr(investment, cash_flows)

            deposit_profit = investment * (deposit_rate / 100) * (term_months / 12) if term_months > 0 else 0
            diff_vs_deposit = profit - deposit_profit

            npv = None
            if discount_enabled and discount_rate > 0:
                npv = -investment
                for cf in cash_flows:
                    years = cf['months'] / 12
                    npv += cf['amount'] / pow(1 + discount_rate/100, years)

            history_data = {
                'date': datetime.now().isoformat(),
                'investment': investment,
                'method': method,
                'mode': mode,
                'term_months': term_months,
                'total_return': total_return,
                'profit': profit,
                'rate': annual_rate if mode == 'loan' else '',
                'dividends': dividends if mode == 'share' else '',
                'exit_price': exit_price if mode == 'share' and sell_share == 'true' else 0,
                'roi': roi,
                'annual_return': annual_return,
                'deposit_rate': deposit_rate,
                'discount_rate': discount_rate if discount_enabled else 0,
                'npv': npv,
                'irr': irr
            }
            db.save_history(history_data)

            result = {
                'investment': investment,
                'total_return': total_return,
                'profit': profit,
                'roi': roi,
                'annual_return': annual_return,
                'irr': irr,
                'deposit_comparison': diff_vs_deposit,
                'deposit_rate': deposit_rate,
                'discount_enabled': discount_enabled,
                'discount_rate': discount_rate,
                'npv': npv
            }
        except Exception as e:
            error = str(e)

    return render_template('calculator.html',
                           result=result,
                           error=error,
                           investment=investment,
                           method=method,
                           mode=mode,
                           expected_return=expected_return,
                           dividends=dividends,
                           sell_share=sell_share,
                           exit_price=exit_price,
                           term_months_loan=term_months_loan,
                           annual_rate=annual_rate,
                           deposit_rate=deposit_rate,
                           discount_enabled=discount_enabled,
                           discount_rate=discount_rate,
                           term_months_common=term_months_common)

@app.route('/history')
def history():
    records = db.get_history()
    return render_template('history.html', records=records)

@app.route('/delete_history/<int:record_id>')
def delete_history(record_id):
    db.delete_history_record(record_id)
    flash('Запись удалена', 'success')
    return redirect(url_for('calculator_root'))

@app.route('/export_history_excel')
def export_history_excel():
    data = db.export_history_to_excel()
    return send_file(
        io.BytesIO(data),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name='history.xlsx'
    )

# -------------------- ОПЕРАЦИИ --------------------
@app.route('/add_operation', methods=['GET', 'POST'])
def add_operation():
    projects = db.get_projects()
    if request.method == 'POST':
        date = request.form.get('date')
        project_id = request.form.get('project_id')
        if project_id == '':
            project_id = None
        else:
            project_id = int(project_id)
        amount = float(request.form.get('amount', 0))
        type_ = request.form.get('type')
        category = request.form.get('category', '')
        comment = request.form.get('comment', '')
        if not date or amount <= 0:
            flash('Заполните дату и сумму', 'error')
            return render_template('add_operation.html', projects=projects)
        db.add_operation(date, project_id, amount, type_, category, comment)
        flash('Операция добавлена!', 'success')
        return redirect(url_for('operations_root'))
    return render_template('add_operation.html', projects=projects)

@app.route('/delete_operation/<int:op_id>')
def delete_operation(op_id):
    db.delete_operation(op_id)
    flash('Операция удалена', 'success')
    return redirect(url_for('operations_root'))

@app.route('/operations_list')
def operations_list():
    ops = db.get_operations()
    return render_template('operations_list.html', operations=ops)

@app.route('/export_operations_excel')
def export_operations_excel():
    data = db.export_operations_to_excel()
    return send_file(
        io.BytesIO(data),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name='operations.xlsx'
    )

# -------------------- ПРОЕКТЫ --------------------
@app.route('/projects', methods=['GET', 'POST'])
def projects():
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add':
            name = request.form.get('name')
            comment = request.form.get('comment', '')
            type_ = request.form.get('type', 'Доля')
            share_percent = request.form.get('share_percent')
            if share_percent == '':
                share_percent = None
            else:
                share_percent = float(share_percent)
            investment_amount = request.form.get('investment_amount')
            if investment_amount == '':
                investment_amount = None
            else:
                investment_amount = float(investment_amount)
            contract_number = request.form.get('contract_number', '')
            if name:
                db.add_project(name, comment, type_, share_percent, investment_amount, contract_number)
                flash('Проект добавлен', 'success')
        elif action == 'delete':
            project_id = request.form.get('project_id')
            if project_id:
                db.delete_project(project_id)
                flash('Проект удалён', 'success')
        return redirect(url_for('projects_root'))
    projects_list = db.get_projects()
    return render_template('projects.html', projects=projects_list)

@app.route('/graphics', methods=['GET', 'POST'])
def graphics():
    projects = db.get_projects()
    if request.method == 'POST':
        project_id = request.form.get('project_id')
        if not project_id:
            flash('Выберите проект', 'error')
            return redirect(url_for('projects_root'))
        file = request.files.get('file')
        if not file or file.filename == '':
            flash('Выберите файл', 'error')
            return redirect(url_for('projects_root'))
        if not (file.filename.endswith('.xlsx') or file.filename.endswith('.xls')):
            flash('Поддерживаются только Excel файлы (.xlsx, .xls)', 'error')
            return redirect(url_for('projects_root'))
        try:
            df = pd.read_excel(file, engine='openpyxl' if file.filename.endswith('.xlsx') else 'xlrd')
            cols = df.columns.tolist()
            date_col = None
            amount_col = None
            for col in cols:
                if 'дата' in col.lower() or 'date' in col.lower():
                    date_col = col
                if 'сумма' in col.lower() or 'amount' in col.lower():
                    amount_col = col
            if date_col is None or amount_col is None:
                flash('Файл должен содержать колонки "Дата" и "Сумма"', 'error')
                return redirect(url_for('projects_root'))
            rows = []
            for idx, row in df.iterrows():
                date_val = row[date_col]
                amount_val = row[amount_col]
                if pd.isna(date_val) or pd.isna(amount_val):
                    continue
                if isinstance(date_val, datetime):
                    date_str = date_val.strftime('%Y-%m-%d')
                else:
                    date_str = str(date_val)
                amount = float(amount_val)
                rows.append((date_str, amount))
            if not rows:
                flash('Нет данных для загрузки', 'error')
                return redirect(url_for('projects_root'))
            db.add_payments_from_excel(int(project_id), rows)
            project_name = next((p['name'] for p in projects if p['id'] == int(project_id)), '')
            flash(f'Загружено {len(rows)} платежей для проекта "{project_name}"', 'success')
        except Exception as e:
            flash(f'Ошибка обработки файла: {str(e)}', 'error')
        return redirect(url_for('projects_root'))
    return render_template('graphics.html', projects=projects)

# -------------------- PWA --------------------
@app.route('/manifest.json')
def manifest():
    return app.send_static_file('manifest.json')

@app.route('/sw.js')
def service_worker():
    return app.send_static_file('sw.js')

# -------------------- КОНТАКТЫ И ИНСТРУКЦИЯ --------------------
@app.route('/contacts')
def contacts():
    return render_template('contacts.html')

@app.route('/instructions')
def instructions():
    return render_template('instructions.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)
