CREATE OR REPLACE PACKAGE BODY payroll_engine AS

    FUNCTION get_tax_bracket(
        p_salary    IN NUMBER,
        p_country   IN VARCHAR2,
        p_year      IN NUMBER
    ) RETURN NUMBER AS
        v_rate NUMBER := 0;
    BEGIN
        IF p_country = 'US' THEN
            IF p_salary > 500000 THEN
                v_rate := 0.37;
            ELSIF p_salary > 200000 THEN
                v_rate := 0.32;
            ELSIF p_salary > 100000 THEN
                v_rate := 0.24;
            ELSIF p_salary > 50000 THEN
                v_rate := 0.22;
            ELSIF p_salary > 20000 THEN
                v_rate := 0.12;
            ELSE
                v_rate := 0.10;
            END IF;
        ELSIF p_country = 'UK' THEN
            IF p_salary > 150000 THEN
                v_rate := 0.45;
            ELSIF p_salary > 50270 THEN
                v_rate := 0.40;
            ELSIF p_salary > 12570 THEN
                v_rate := 0.20;
            ELSE
                v_rate := 0;
            END IF;
        ELSIF p_country = 'DE' THEN
            IF p_salary > 277825 THEN
                v_rate := 0.45;
            ELSIF p_salary > 62809 THEN
                v_rate := 0.42;
            ELSIF p_salary > 17005 THEN
                v_rate := 0.14 + (p_salary - 17005) * 0.0000022;
            ELSE
                v_rate := 0;
            END IF;
        ELSE
            v_rate := 0.25;
        END IF;

        RETURN v_rate;
    END get_tax_bracket;

    PROCEDURE run_monthly_payroll(
        p_period_year  IN NUMBER,
        p_period_month IN NUMBER,
        p_dry_run      IN BOOLEAN DEFAULT FALSE
    ) AS
        CURSOR c_active_employees IS
            SELECT e.employee_id,
                   e.salary,
                   e.job_id,
                   e.department_id,
                   e.country_code,
                   e.hire_date,
                   NVL(e.fte, 1) AS fte
              FROM employees e
             WHERE e.status = 'ACTIVE'
               AND e.termination_date IS NULL
             ORDER BY e.department_id, e.employee_id;

        CURSOR c_deductions(p_emp_id IN NUMBER) IS
            SELECT deduction_type, amount, is_percentage
              FROM employee_deductions
             WHERE employee_id = p_emp_id
               AND effective_date <= LAST_DAY(TO_DATE(p_period_year || '-' || p_period_month, 'YYYY-MM'))
               AND (end_date IS NULL OR end_date >= TRUNC(TO_DATE(p_period_year || '-' || p_period_month, 'YYYY-MM'), 'MM'))
             ORDER BY deduction_type;

        v_gross_pay      NUMBER;
        v_tax_rate       NUMBER;
        v_tax_amount     NUMBER;
        v_deduction_total NUMBER;
        v_net_pay        NUMBER;
        v_overtime_pay   NUMBER;
        v_overtime_hours NUMBER;
        v_ytd_gross      NUMBER;
        v_bonus_eligible BOOLEAN;
        v_pay_period_days NUMBER;
        v_errors         NUMBER := 0;
        v_processed      NUMBER := 0;
    BEGIN
        v_pay_period_days := CASE
            WHEN p_period_month IN (1, 3, 5, 7, 8, 10, 12) THEN 31
            WHEN p_period_month IN (4, 6, 9, 11)            THEN 30
            WHEN MOD(p_period_year, 400) = 0                THEN 29
            WHEN MOD(p_period_year, 100) = 0                THEN 28
            WHEN MOD(p_period_year, 4) = 0                  THEN 29
            ELSE 28
        END;

        FOR emp IN c_active_employees LOOP
            BEGIN
                -- base gross for the month
                v_gross_pay := emp.salary / 12 * emp.fte;

                -- overtime lookup
                BEGIN
                    SELECT NVL(SUM(hours_worked) - 160, 0)
                      INTO v_overtime_hours
                      FROM timesheets
                     WHERE employee_id = emp.employee_id
                       AND EXTRACT(YEAR FROM work_date)  = p_period_year
                       AND EXTRACT(MONTH FROM work_date) = p_period_month;
                EXCEPTION
                    WHEN NO_DATA_FOUND THEN
                        v_overtime_hours := 0;
                END;

                IF v_overtime_hours > 0 THEN
                    v_overtime_pay := (emp.salary / 12 / 160) * v_overtime_hours * 1.5;
                ELSIF v_overtime_hours < -40 THEN
                    -- significant shortfall — flag but do not dock
                    INSERT INTO payroll_warnings(employee_id, period_year, period_month, warning_type, detail)
                    VALUES (emp.employee_id, p_period_year, p_period_month, 'LOW_HOURS',
                            'Logged only ' || (160 + v_overtime_hours) || 'h');
                    v_overtime_pay := 0;
                ELSE
                    v_overtime_pay := 0;
                END IF;

                v_gross_pay := v_gross_pay + v_overtime_pay;

                -- year-to-date for bracket blending
                SELECT NVL(SUM(gross_pay), 0)
                  INTO v_ytd_gross
                  FROM payroll_runs
                 WHERE employee_id = emp.employee_id
                   AND period_year = p_period_year
                   AND period_month < p_period_month;

                v_tax_rate   := get_tax_bracket(v_ytd_gross + v_gross_pay, emp.country_code, p_period_year);
                v_tax_amount := v_gross_pay * v_tax_rate;

                -- deductions
                v_deduction_total := 0;
                FOR ded IN c_deductions(emp.employee_id) LOOP
                    IF ded.is_percentage = 'Y' THEN
                        v_deduction_total := v_deduction_total + v_gross_pay * ded.amount / 100;
                    ELSE
                        v_deduction_total := v_deduction_total + ded.amount;
                    END IF;
                END LOOP;

                v_net_pay := v_gross_pay - v_tax_amount - v_deduction_total;

                IF v_net_pay < 0 THEN
                    INSERT INTO payroll_warnings(employee_id, period_year, period_month, warning_type, detail)
                    VALUES (emp.employee_id, p_period_year, p_period_month, 'NEGATIVE_NET',
                            'Net pay would be ' || ROUND(v_net_pay, 2));
                    v_net_pay := 0;
                END IF;

                -- bonus eligibility: tenured, rated, not on PIP
                v_bonus_eligible := FALSE;
                IF MONTHS_BETWEEN(SYSDATE, emp.hire_date) >= 12 THEN
                    IF NOT EXISTS (
                        SELECT 1 FROM pip_records
                         WHERE employee_id = emp.employee_id
                           AND status = 'ACTIVE'
                    ) THEN
                        v_bonus_eligible := TRUE;
                    END IF;
                END IF;

                IF NOT p_dry_run THEN
                    INSERT INTO payroll_runs(
                        employee_id, period_year, period_month,
                        gross_pay, tax_amount, deductions, net_pay,
                        overtime_pay, bonus_eligible, run_timestamp
                    ) VALUES (
                        emp.employee_id, p_period_year, p_period_month,
                        v_gross_pay, v_tax_amount, v_deduction_total, v_net_pay,
                        v_overtime_pay,
                        CASE WHEN v_bonus_eligible THEN 'Y' ELSE 'N' END,
                        SYSTIMESTAMP
                    );
                END IF;

                v_processed := v_processed + 1;

            EXCEPTION
                WHEN ZERO_DIVIDE THEN
                    v_errors := v_errors + 1;
                    INSERT INTO payroll_errors(employee_id, period_year, period_month, error_msg)
                    VALUES (emp.employee_id, p_period_year, p_period_month, 'Division by zero in pay calculation');
                WHEN OTHERS THEN
                    v_errors := v_errors + 1;
                    INSERT INTO payroll_errors(employee_id, period_year, period_month, error_msg)
                    VALUES (emp.employee_id, p_period_year, p_period_month, SQLERRM);
            END;
        END LOOP;

        IF NOT p_dry_run THEN
            COMMIT;
        END IF;

        DBMS_OUTPUT.PUT_LINE('Payroll ' || p_period_year || '-' || LPAD(p_period_month, 2, '0')
            || ': processed=' || v_processed
            || ', errors=' || v_errors
            || CASE WHEN p_dry_run THEN ' (DRY RUN)' ELSE '' END);

    EXCEPTION
        WHEN OTHERS THEN
            ROLLBACK;
            RAISE;
    END run_monthly_payroll;

END payroll_engine;
/
