/* plsql_logic.sql
   Практические примеры логики на стороне Oracle Database

   Содержимое:
   1. Функция определения операций пополнения счета
   2. Процедура выгрузки страховых взносов ИП с логированием
   3. Пакет управления бронированиями авиаперевозок
   4. Триггер проверки паспортных реквизитов
   5. Планировщик DBMS_SCHEDULER
   6. Материализованное представление для ускорения запроса

   Назначение:
   - показать навыки PL/SQL
   - показать работу с функциями, процедурами, пакетами, триггерами
   - показать использование служебных механизмов Oracle
*/


/* 1. ФУНКЦИЯ popолнения счета
   Что делает:
   - по идентификатору операции определяет, относится ли она
     к операциям пополнения счета
   - возвращает:
       1 — операция соответствует шаблону
       0 — операция не соответствует
   - используется регулярное выражение по полю descr */

CREATE OR REPLACE FUNCTION popoln(op_id IN NUMBER)
RETURN NUMBER
IS
    v_result NUMBER := 0;
    v_descr  VARCHAR2(255);
BEGIN
    SELECT descr
      INTO v_descr
      FROM sh.test_operation
     WHERE kod = op_id;

    IF REGEXP_LIKE(LOWER(v_descr), 'внесение|пополнение|увеличение|зачисление|зарплата') THEN
        v_result := 1;
    ELSE
        v_result := 0;
    END IF;

    RETURN v_result;

EXCEPTION
    WHEN NO_DATA_FOUND THEN
        RETURN 0;
END;


/* вызов:
SET SERVEROUTPUT ON;
DECLARE
    v_result NUMBER;
BEGIN
    v_result := popoln(1);
    DBMS_OUTPUT.PUT_LINE('Результат: ' || v_result);
END;
*/


/* 2. ПРОЦЕДУРА ВЫГРУЗКИ ОПЕРАЦИЙ ИП С ЛОГИРОВАНИЕМ
   Что делает:
   - отбирает операции страховых взносов, где плательщик — ИП
   - принимает период (DateFrom, DateTo)
   - пишет результат во временную таблицу
   - создает отдельную итоговую таблицу с уникальным именем
   - фиксирует ход выполнения в таблице лога */

--- Таблицы и последовательность для процедуры

CREATE TABLE oper_ip (
    kod NUMBER,
    data_op DATE,
    naimen VARCHAR2(255),
    descr VARCHAR2(255)
);

CREATE GLOBAL TEMPORARY TABLE temp_oper_ip (
    kod NUMBER,
    data_op DATE,
    naimen VARCHAR2(255),
    descr VARCHAR2(255)
) ON COMMIT PRESERVE ROWS;

CREATE TABLE log_table_ip (
    id NUMBER PRIMARY KEY,
    rec_date DATE NOT NULL,
    dt_from DATE NOT NULL,
    dt_to DATE NOT NULL,
    row_count NUMBER,
    proc_end DATE,
    proc_status NUMBER(1)
);

CREATE SEQUENCE seq_proc_log_ip_id
START WITH 1
INCREMENT BY 1
NOMAXVALUE;

--- Процедура
CREATE OR REPLACE PROCEDURE ip_from_to(DateFrom IN DATE, DateTo IN DATE)
IS
    v_row_count  NUMBER := 0;
    v_log_id     NUMBER;
    v_table_name VARCHAR2(50);
BEGIN
    DELETE FROM temp_oper_ip;
    COMMIT;

    v_log_id := seq_proc_log_ip_id.NEXTVAL;

    INSERT INTO log_table_ip (id, rec_date, dt_from, dt_to)
    VALUES (v_log_id, SYSDATE, DateFrom, DateTo);
    COMMIT;

    FOR oper_rec IN (
        SELECT op.kod,
               op.data_op,
               uch.naimen,
               op.descr
          FROM sh.test_operation op
          JOIN sh.test_uchast uch
            ON op.inn_pl = uch.inn
         WHERE op.data_op BETWEEN DateFrom AND DateTo
           AND REGEXP_LIKE(
                   UPPER(uch.naimen),
                   '(^|\s)(ИП|ЧП|ПБОЮЛ|ИЧП|ИНДИВИДУАЛЬНЫЙ\s+ПРЕДПРИНИМАТЕЛЬ|ИНДИВИД\w*\s+ПРЕД\w*|ПРЕДПРИНИМАТЕЛЬ\s+БЕЗ\s+ОБРАЗ\w*\s+ЮР\w*|ПРЕДПРИНИМАТЕЛЬ)(\s|$)'
               )
           AND REGEXP_LIKE(
                   LOWER(op.descr),
                   'страх(\.|овой)?\s+взн(\.|ос)?'
               )
    ) LOOP
        v_row_count := v_row_count + 1;

        INSERT INTO temp_oper_ip (kod, data_op, naimen, descr)
        VALUES (oper_rec.kod, oper_rec.data_op, oper_rec.naimen, oper_rec.descr);
    END LOOP;

    COMMIT;

    UPDATE log_table_ip
       SET row_count   = v_row_count,
           proc_end    = SYSDATE,
           proc_status = 1
     WHERE id = v_log_id;
    COMMIT;

    IF v_row_count > 0 THEN
        v_table_name := 'oper_ip_' || v_log_id;

        EXECUTE IMMEDIATE '
            CREATE TABLE ' || v_table_name || ' (
                kod NUMBER,
                data_op DATE,
                naimen VARCHAR2(255),
                descr VARCHAR2(255)
            )';

        EXECUTE IMMEDIATE '
            INSERT INTO ' || v_table_name || ' (kod, data_op, naimen, descr)
            SELECT kod, data_op, naimen, descr
              FROM temp_oper_ip';

        COMMIT;
    END IF;

EXCEPTION
    WHEN OTHERS THEN
        UPDATE log_table_ip
           SET row_count   = v_row_count,
               proc_end    = SYSDATE,
               proc_status = 0
         WHERE id = v_log_id;
        COMMIT;
        RAISE;
END;

/* вызов:
BEGIN
    ip_from_to(
        TO_DATE('01.01.2009', 'DD.MM.YYYY'),
        TO_DATE('29.12.2012', 'DD.MM.YYYY')
    );
END;

Проверка:
SELECT * FROM log_table_ip ORDER BY id;
*/


/* 3. ПАКЕТ BookingManagementPackage
   Что делает:
   - возвращает список доступных рейсов
   - возвращает детали конкретного рейса
   - отменяет бронирование при соблюдении условий
   - использует backup-таблицы для безопасной отмены */

--- Вспомогательные таблицы для учебного контура

CREATE TABLE my_booking AS SELECT * FROM avia.bookings WHERE 1 = 0;
CREATE TABLE my_tickets AS SELECT * FROM avia.tickets WHERE 1 = 0;
CREATE TABLE my_ticket_flights AS SELECT * FROM avia.ticket_flights WHERE 1 = 0;

CREATE TABLE my_flights AS SELECT * FROM avia.flights WHERE 1 = 0;
CREATE TABLE my_airports_data AS SELECT * FROM avia.airports_data WHERE 1 = 0;
CREATE TABLE my_aircrafts AS SELECT * FROM avia.aircrafts_data   WHERE 1 = 0;
CREATE TABLE my_seats AS SELECT * FROM avia.seats WHERE 1 = 0;
CREATE TABLE my_boarding_passes AS SELECT * FROM avia.boarding_passes WHERE 1 = 0;

CREATE TABLE my_bookings_backup AS SELECT * FROM my_booking WHERE 1 = 0;
CREATE TABLE my_tickets_backup AS SELECT * FROM my_tickets WHERE 1 = 0;
CREATE TABLE my_ticket_flights_backup AS SELECT * FROM my_ticket_flights WHERE 1 = 0;

--- Спецификация пакета

CREATE OR REPLACE PACKAGE BookingManagementPackage AS
    TYPE FlightList IS TABLE OF avia.flights%ROWTYPE;

    FUNCTION GetAvailableFlights
        RETURN FlightList PIPELINED;

    FUNCTION GetFlightDetails(p_flight_id NUMBER)
        RETURN avia.flights%ROWTYPE;

    PROCEDURE CancelBooking(p_book_ref VARCHAR2);
END BookingManagementPackage;

--- Тело

CREATE OR REPLACE PACKAGE BODY BookingManagementPackage AS

    v_current_date TIMESTAMP := TO_TIMESTAMP('2017-04-01 12:00:00', 'YYYY-MM-DD HH24:MI:SS');

    /* Функция GetAvailableFlights
       Возвращает доступные рейсы:
       - статус Scheduled
       - вылет еще не произошел
       - есть свободные места */
    FUNCTION GetAvailableFlights
        RETURN FlightList PIPELINED
    IS
    BEGIN
        FOR rec IN (
            SELECT f.*
              FROM avia.flights f
             WHERE f.status = 'Scheduled'
               AND f.scheduled_departure > v_current_date
               AND (
                    SELECT COUNT(*)
                      FROM avia.ticket_flights tf
                     WHERE tf.flight_id = f.flight_id
               ) < (
                    SELECT COUNT(*)
                      FROM avia.seats s
                     WHERE s.aircraft_code = f.aircraft_code
               )
        ) LOOP
            PIPE ROW (rec);
        END LOOP;

        RETURN;
    END GetAvailableFlights;


--- Функция GetFlightDetails возвращает полную строку рейса по flight_id 
    FUNCTION GetFlightDetails(p_flight_id NUMBER)
        RETURN avia.flights%ROWTYPE
    IS
        v_flight avia.flights%ROWTYPE;
    BEGIN
        SELECT *
          INTO v_flight
          FROM avia.flights
         WHERE flight_id = p_flight_id;

        RETURN v_flight;

    EXCEPTION
        WHEN NO_DATA_FOUND THEN
            RAISE_APPLICATION_ERROR(-20001, 'Рейс не найден');
    END GetFlightDetails;


    /* Процедура CancelBooking
       Что делает:
       - проверяет существование бронирования
       - проверяет, что до вылета более 24 часов
       - сохраняет удаляемые строки в backup-таблицы
       - удаляет бронь и связанные записи */
    PROCEDURE CancelBooking(p_book_ref VARCHAR2)
    IS
        v_count          NUMBER;
        v_flight_id      my_ticket_flights.flight_id%TYPE;
        v_departure_time avia.flights.scheduled_departure%TYPE;

        CURSOR c_tickets IS
            SELECT *
              FROM my_tickets
             WHERE book_ref = p_book_ref;
    BEGIN
        SELECT COUNT(*)
          INTO v_count
          FROM my_booking
         WHERE book_ref = p_book_ref;

        IF v_count = 0 THEN
            RAISE_APPLICATION_ERROR(-20002, 'Бронирование не найдено');
        END IF;

        FOR rec IN c_tickets LOOP
            SELECT flight_id
              INTO v_flight_id
              FROM my_ticket_flights
             WHERE ticket_no = rec.ticket_no;

            v_departure_time := GetFlightDetails(v_flight_id).scheduled_departure;

            IF v_departure_time - v_current_date < INTERVAL '1' DAY THEN
                RAISE_APPLICATION_ERROR(-20003, 'Отмена возможна только более чем за 24 часа до вылета');
            END IF;

            INSERT INTO my_tickets_backup
            SELECT *
              FROM my_tickets
             WHERE ticket_no = rec.ticket_no;

            INSERT INTO my_ticket_flights_backup
            SELECT *
              FROM my_ticket_flights
             WHERE ticket_no = rec.ticket_no;

            DELETE FROM my_ticket_flights
             WHERE ticket_no = rec.ticket_no;

            DELETE FROM my_tickets
             WHERE ticket_no = rec.ticket_no;
        END LOOP;

        INSERT INTO my_bookings_backup
        SELECT *
          FROM my_booking
         WHERE book_ref = p_book_ref;

        DELETE FROM my_booking
         WHERE book_ref = p_book_ref;
    END CancelBooking;

END BookingManagementPackage;

/* примеры вызова:

-- доступные рейсы
SELECT * FROM TABLE(BookingManagementPackage.GetAvailableFlights);

-- детали рейса
SET SERVEROUTPUT ON;
DECLARE
    v_flight avia.flights%ROWTYPE;
BEGIN
    v_flight := BookingManagementPackage.GetFlightDetails(430);

    DBMS_OUTPUT.PUT_LINE('Flight No: ' || v_flight.flight_no);
    DBMS_OUTPUT.PUT_LINE('Departure: ' || v_flight.scheduled_departure);
    DBMS_OUTPUT.PUT_LINE('Arrival: ' || v_flight.scheduled_arrival);
    DBMS_OUTPUT.PUT_LINE('From: ' || v_flight.departure_airport || ' To: ' || v_flight.arrival_airport);
END;

-- отмена бронирования
BEGIN
    BookingManagementPackage.CancelBooking('01679D');
END;
*/


/*4. ТРИГГЕР ПРОВЕРКИ ПАСПОРТНЫХ ДАННЫХ
   Что делает:
   - проверяет формат серии и номера документа у физлиц
   - учитывает тип документа и возраст
   - поддерживает несколько вариантов:
       ПасРФ, ПасЗаг, СвдРжд, ПасИнс
   - при успешной вставке пишет запись в audit-таблицу */


--- Таблицы

CREATE TABLE uch_vse_2014 (
    inn VARCHAR2(256),
    naimen VARCHAR2(256),
    amr0 VARCHAR2(256),
    rg0 VARCHAR2(256),
    sd0 VARCHAR2(256),
    gr0 DATE,
    doc VARCHAR2(256),
    strana VARCHAR2(256)
);

CREATE TABLE control_changes (
    id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_name VARCHAR2(256),
    insert_date DATE DEFAULT SYSDATE,
    inn VARCHAR2(256),
    naimen VARCHAR2(256)
);

--- Триггер
CREATE OR REPLACE TRIGGER check_passport
BEFORE INSERT ON uch_vse_2014
FOR EACH ROW
DECLARE
    v_age NUMBER;
BEGIN
    IF :new.gr0 IS NOT NULL THEN
        v_age := FLOOR(MONTHS_BETWEEN(SYSDATE, :new.gr0) / 12);
    ELSE
        v_age := NULL;
    END IF;

    /* Проверка выполняется только для физлица:
       считаем, что ИНН физлица состоит из 12 цифр */
    IF REGEXP_LIKE(:new.inn, '^\d{12}$') THEN

        /* Иностранный документ */
        IF :new.doc = 'ПасИнс' THEN
            IF :new.strana IS NULL THEN
                RAISE_APPLICATION_ERROR(-20001, 'Для ПасИнс необходимо указать страну.');
            END IF;

            IF :new.strana = 'Испания' THEN
                IF NOT REGEXP_LIKE(:new.rg0 || :new.sd0, '^[A-Z]{2}\d{6}$') THEN
                    RAISE_APPLICATION_ERROR(-20001, 'Формат испанского паспорта: 2 латинские буквы + 6 цифр.');
                END IF;

            ELSIF :new.strana = 'Тайвань' THEN
                IF NOT REGEXP_LIKE(:new.rg0 || :new.sd0, '^[A-Z][12]\d{8}$') THEN
                    RAISE_APPLICATION_ERROR(-20001, 'Формат тайваньского удостоверения: 1 лат. буква + [1/2] + 8 цифр.');
                END IF;

            ELSE
                RAISE_APPLICATION_ERROR(-20001, 'Проверка для указанной страны не реализована.');
            END IF;

        /* Для граждан РФ дата рождения обязательна */
        ELSIF v_age IS NULL THEN
            RAISE_APPLICATION_ERROR(-20001, 'Дата рождения обязательна для физлица (кроме ПасИнс).');

        /* До 14 лет */
        ELSIF v_age < 14 THEN
            IF :new.doc = 'ПасЗаг' THEN
                IF NOT REGEXP_LIKE(:new.rg0, '^\d{2}$') THEN
                    RAISE_APPLICATION_ERROR(-20001, 'Серия загранпаспорта: 2 цифры.');
                END IF;

                IF NOT REGEXP_LIKE(:new.sd0, '^\d{7}$') THEN
                    RAISE_APPLICATION_ERROR(-20001, 'Номер загранпаспорта: 7 цифр.');
                END IF;

            ELSIF :new.doc = 'СвдРжд' THEN
                IF NOT REGEXP_LIKE(:new.rg0, '^[IVXLCDM]+-[А-ЯЁ]{2}$') THEN
                    RAISE_APPLICATION_ERROR(-20001, 'Серия свидетельства: римские цифры, "-", 2 русские буквы.');
                END IF;

                IF NOT REGEXP_LIKE(:new.sd0, '^\d{6}$') THEN
                    RAISE_APPLICATION_ERROR(-20001, 'Номер свидетельства: 6 цифр.');
                END IF;

            ELSE
                RAISE_APPLICATION_ERROR(-20001, 'Для младше 14 лет допустимы только ПасЗаг или СвдРжд.');
            END IF;

        /* 14 лет и старше */
        ELSE
            IF :new.doc = 'ПасРФ' THEN
                IF NOT REGEXP_LIKE(:new.rg0, '^\d{4}$') THEN
                    RAISE_APPLICATION_ERROR(-20001, 'Серия паспорта РФ: 4 цифры.');
                END IF;

                IF NOT REGEXP_LIKE(:new.sd0, '^\d{6}$') THEN
                    RAISE_APPLICATION_ERROR(-20001, 'Номер паспорта РФ: 6 цифр.');
                END IF;

            ELSE
                RAISE_APPLICATION_ERROR(-20001, 'Для 14+ лет допустим только ПасРФ.');
            END IF;
        END IF;
    END IF;

    INSERT INTO control_changes (user_name, insert_date, inn, naimen)
    VALUES (USER, SYSDATE, :new.inn, :new.naimen);
END;

/*
Примеры вставки для проверки:

-- юрлицо
INSERT INTO uch_vse_2014 (inn, naimen, amr0, rg0, sd0, gr0, doc, strana)
VALUES ('1234567890', 'ООО Ромашка', 'Москва', NULL, NULL, DATE '2020-01-01', NULL, NULL);

-- физлицо, паспорт РФ
INSERT INTO uch_vse_2014 (inn, naimen, amr0, rg0, sd0, gr0, doc, strana)
VALUES ('123456789012', 'Иванов Иван Иванович', 'Москва', '1234', '123456', DATE '1990-05-10', 'ПасРФ', NULL);
*/


/* 5. ПЛАНИРОВЩИК DBMS_SCHEDULER
   Что делает:
   - создает задачу на регулярный запуск статистики
   - пример: каждую третью среду месяца в 03:08 */

BEGIN
    DBMS_SCHEDULER.DROP_JOB(
        job_name => 'GATHER_SALES_STATS_JOB',
        force    => TRUE
    );
EXCEPTION
    WHEN OTHERS THEN
        NULL;
END;
/

BEGIN
    DBMS_SCHEDULER.CREATE_JOB(
        job_name        => 'GATHER_SALES_STATS_JOB',
        job_type        => 'PLSQL_BLOCK',
        job_action      => q'[
            BEGIN
                DBMS_STATS.GATHER_TABLE_STATS(
                    'KA2206_12',
                    'SALES',
                    method_opt => 'FOR COLUMNS (empno, deptno)'
                );
            END;
        ]',
        start_date      => SYSTIMESTAMP,
        repeat_interval => 'FREQ=MONTHLY;BYDAY=WED;BYSETPOS=3;BYHOUR=3;BYMINUTE=8;BYSECOND=0',
        enabled         => TRUE,
        comments        => 'Сбор статистики для таблицы SALES в третью среду месяца'
    );
END;

/*
Проверка:
SELECT *
  FROM dba_scheduler_jobs
 WHERE job_name = 'GATHER_SALES_STATS_JOB';
*/


/* 6. МАТЕРИАЛИЗОВАННОЕ ПРЕДСТАВЛЕНИЕ
   Что делает:
   - кэширует результат тяжелого запроса по авиаперевозкам
   - полностью обновляется раз в неделю
   - используется для снижения стоимости выполнения запроса */

CREATE MATERIALIZED VIEW my_mv_svo_flights
REFRESH COMPLETE
START WITH SYSDATE
NEXT SYSDATE + 7
AS
SELECT DISTINCT
       t.passenger_name,
       t.passenger_id,
       f.flight_no,
       f.scheduled_departure,
       f.departure_airport
  FROM avia.tickets t
  JOIN avia.ticket_flights tf
    ON t.ticket_no = tf.ticket_no
  JOIN avia.flights f
    ON tf.flight_id = f.flight_id
 WHERE f.departure_airport = 'SVO'
   AND f.scheduled_departure BETWEEN TO_DATE('2022-01-01', 'YYYY-MM-DD')
                                 AND TO_DATE('2022-02-01', 'YYYY-MM-DD');

/* Проверка плана:
EXPLAIN PLAN FOR
SELECT * FROM my_mv_svo_flights;

SELECT * FROM TABLE(DBMS_XPLAN.DISPLAY);
*/