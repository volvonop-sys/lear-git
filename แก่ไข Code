async function claimInsurance(db, patientId, treatmentCost) {
    const client = await db.connect();

    try {
        await client.query('BEGIN');

        const selectQuery = 'SELECT limit_amount FROM patients WHERE id = $1 FOR UPDATE';
        const result = await client.query(selectQuery, [patientId]);

        if (result.rows.length === 0) {
            throw new Error('ไม่พบข้อมูลผู้ป่วยรายนี้ในระบบ');
        }

        const currentLimit = result.rows[0].limit_amount;

        if (currentLimit >= treatmentCost) {
            const newLimit = currentLimit - treatmentCost;

            const updateQuery = 'UPDATE patients SET limit_amount = $1 WHERE id = $2';
            await client.query(updateQuery, [newLimit, patientId]);

            await client.query('COMMIT');
            return { success: true, remainingLimit: newLimit };
        } else {
            await client.query('ROLLBACK');
            return { success: false, error: 'วงเงินประกันคงเหลือไม่เพียงพอสำหรับหักค่ารักษา' };
        }

    } catch (error) {
        await client.query('ROLLBACK');
        return { success: false, error: error.message };
    } finally {
        client.release();
    }
}

module.exports = { claimInsurance };
