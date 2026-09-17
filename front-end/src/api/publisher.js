import axios from "axios";

const PUBLISHER_BASE_URL = "http://localhost:8005";

export async function publishRecord(recordId) {
    const response = await axios.post(`${PUBLISHER_BASE_URL}/publish`, {
        record_id: recordId,
    });

    return response.data;
}
