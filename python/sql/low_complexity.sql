CREATE OR REPLACE PROCEDURE update_employee_salary(
    p_employee_id IN NUMBER,
    p_new_salary  IN NUMBER
) AS
BEGIN
    UPDATE employees
       SET salary = p_new_salary,
           updated_at = SYSDATE
     WHERE employee_id = p_employee_id;

    COMMIT;
END update_employee_salary;
/

CREATE OR REPLACE FUNCTION get_employee_name(
    p_employee_id IN NUMBER
) RETURN VARCHAR2 AS
    v_name VARCHAR2(200);
BEGIN
    SELECT first_name || ' ' || last_name
      INTO v_name
      FROM employees
     WHERE employee_id = p_employee_id;

    RETURN v_name;
END get_employee_name;
/
