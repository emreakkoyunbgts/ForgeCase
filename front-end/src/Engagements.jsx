import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import "./Engagements.css";

function Engagements() {
    const [engagements, setEngagements] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    const navigate = useNavigate();

    useEffect(() => {
        const getEngagements = async () => {
            try {
                const response = await axios.get(
                    "http://localhost:8000/engagements"
                );

                setEngagements(response.data.items);
            } catch (error) {
                console.error("Error fetching engagements:", error);
                setError("Failed to load engagements.");
            } finally {
                setLoading(false);
            }
        };

        getEngagements();
    }, []);

    if (loading) {
        return <div>Loading engagements...</div>;
    }

    if (error) {
        return <div>{error}</div>;
    }

    return (
        <div className="engagements-container">
            <a href="/" className="back-to-engagements">Back to Engagements</a>
            <h1>Engagements</h1>

            {engagements.map((engagement) => (
                <div
                    key={engagement.id}
                    className="engagement-card"
                    onClick={() =>
                        navigate(`/engagements/${engagement.id}`)
                    }
                >
                    <h2>{engagement.id}</h2>

                    <p>
                        <strong>Client Type:</strong>{" "}
                        {engagement.client_type}
                    </p>

                    <p>
                        <strong>Challenge:</strong>{" "}
                        {engagement.challenge}
                    </p>
                </div>
            ))}
        </div>
    );
}

export default Engagements;