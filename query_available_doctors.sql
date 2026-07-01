SELECT d.doctor_id, d.doctor_name
FROM doctors d
-- 1. เชื่อมตารางกะการทำงาน (doctor_shifts) เพื่อเช็กว่าหมอคนไหนเข้าเวรในวันนั้นบ้าง
JOIN doctor_shifts s ON d.doctor_id = s.doctor_id
WHERE s.shift_date = '2026-03-19'
  AND s.start_time <= '10:00:00' 
  AND s.end_time >= '11:00:00'

  -- 2. ดักจับเงื่อนไข "ไม่แสดงแพทย์ที่อยู่ในระหว่างพักกะ (break_time)"
  AND NOT (s.break_start < '11:00:00' AND s.break_end > '10:00:00')

  -- 3. ดักจับเงื่อนไข "ต้องไม่มีนัดที่ status = 'confirmed' ในช่วงเวลาดังกล่าว" และกรณีคาบเกี่ยว (Overlap)
  AND NOT EXISTS (
      SELECT 1 
      FROM appointments a
      WHERE a.doctor_id = d.doctor_id
        AND a.status = 'confirmed'
        AND a.appointment_date = '2026-03-19'
        -- สูตรคำนวณการทับซ้อนของเวลา (Overlap Formula)
        AND a.start_time < '11:00:00' 
        AND a.end_time > '10:00:00'
  );
