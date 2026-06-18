CREATE OR REPLACE PROCEDURE process_department_employees(
    p_dept_id   IN NUMBER,
    p_raise_pct IN NUMBER
) AS
    CURSOR c_employees IS
        SELECT employee_id, salary, job_id
          FROM employees
         WHERE department_id = p_dept_id;

    v_new_salary  NUMBER;
    v_processed   NUMBER := 0;
    v_skipped     NUMBER := 0;
BEGIN
    FOR r IN c_employees LOOP
        IF r.salary IS NULL THEN
            v_skipped := v_skipped + 1;
            CONTINUE;
        END IF;

        IF r.job_id = 'MGR' THEN
            v_new_salary := r.salary * (1 + p_raise_pct / 100 * 1.5);
        ELSIF r.job_id = 'LEAD' THEN
            v_new_salary := r.salary * (1 + p_raise_pct / 100 * 1.2);
        ELSE
            v_new_salary := r.salary * (1 + p_raise_pct / 100);
        END IF;

        UPDATE employees
           SET salary = v_new_salary
         WHERE employee_id = r.employee_id;

        v_processed := v_processed + 1;
    END LOOP;

    COMMIT;

    DBMS_OUTPUT.PUT_LINE('Processed: ' || v_processed || ', Skipped: ' || v_skipped);

EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK;
        RAISE;
END process_department_employees;
/

CREATE OR REPLACE FUNCTION calculate_bonus(
    p_employee_id IN NUMBER,
    p_year        IN NUMBER
) RETURN NUMBER AS
    v_salary      NUMBER;
    v_rating      NUMBER;
    v_bonus       NUMBER := 0;
BEGIN
    SELECT e.salary, NVL(r.rating, 0)
      INTO v_salary, v_rating
      FROM employees e
      LEFT JOIN performance_reviews r
             ON r.employee_id = e.employee_id
            AND r.review_year = p_year
     WHERE e.employee_id = p_employee_id;

    CASE
        WHEN v_rating >= 5 THEN v_bonus := v_salary * 0.20;
        WHEN v_rating >= 4 THEN v_bonus := v_salary * 0.12;
        WHEN v_rating >= 3 THEN v_bonus := v_salary * 0.06;
        ELSE v_bonus := 0;
    END CASE;

    RETURN v_bonus;

EXCEPTION
    WHEN NO_DATA_FOUND THEN
        RETURN 0;
END calculate_bonus;
/
