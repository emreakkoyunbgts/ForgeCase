import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import axios from "axios";
import "./EngagementDetail.css";

const ENGAGEMENTS_API_BASE_URL = "http://localhost:8000";

function getErrorMessage(error, fallback) {
    if (error.response?.data?.detail) return error.response.data.detail;
    return error.request ? "Could not connect to the backend." : fallback;
}

function EngagementDetail() {
    const { id } = useParams();
    const navigate = useNavigate();

    const [engagement, setEngagement] = useState(null);
    const [loading, setLoading] = useState(true);
    const [creatingCaseStudy, setCreatingCaseStudy] = useState(null);
    const [creatingEnglishAiResponse, setCreatingEnglishAiResponse] = useState(false);
    const [deleting, setDeleting] = useState(false);
    const [etag, setEtag] = useState(null);
    const [error, setError] = useState(null);
    const [caseStudy, setCaseStudy] = useState(null);

    useEffect(() => {
        const getEngagement = async () => {
            try {
                const response = await axios.get(
                    `${ENGAGEMENTS_API_BASE_URL}/engagements/${id}`
                );

                setEngagement(response.data);
                setEtag(response.headers.etag || null);
            } catch (error) {
                console.error("Error fetching engagement:", error);
                setError("Failed to load engagement.");
            } finally {
                setLoading(false);
            }
        };

        getEngagement();
    }, [id]);

    const deleteEngagement = async () => {
        if (!engagement || deleting) return;

        const confirmed = window.confirm(
            `Are you sure you want to delete engagement "${engagement.id}"? This action cannot be undone.`
        );

        if (!confirmed) return;

        setDeleting(true);
        setError(null);

        try {
            await axios.delete(`${ENGAGEMENTS_API_BASE_URL}/engagements/${id}`, {
                headers: etag ? { "If-Match": etag } : undefined,
            });
            navigate("/engagements");
        } catch (error) {
            console.error("Error deleting engagement:", error);
            setError(getErrorMessage(error, "The engagement could not be deleted."));
        } finally {
            setDeleting(false);
        }
    };

    const createCaseStudy = async (language = "English") => {
        if (!engagement) {
            return;
        }

        const endpointByLanguage = {
            English: "eng",
            German: "german",
            Turkish: "turkish",
        };

        setCreatingCaseStudy(language);
        setError(null);
        setCaseStudy(null);

        try {
            const response = await axios.post(
                `http://localhost:8001/generator/mcs/${endpointByLanguage[language]}`,
                engagement
            );

            console.log("Case study created:", response.data);

            setCaseStudy({ language, content: response.data });
        } catch (error) {
            console.error("Error creating case study:", error);

            if (error.response) {
                console.error("Status:", error.response.status);
                console.error("Response:", error.response.data);

                setError(
                    `Failed to create case study. Status: ${error.response.status}`
                );
            } else {
                setError("Failed to connect to the server.");
            }
        } finally {
            setCreatingCaseStudy(null);
        }
    };

    const createEnglishAiResponse = async () => {
        if (!engagement) {
            return;
        }

        setCreatingEnglishAiResponse(true);
        setError(null);
        setCaseStudy(null);

        try {
            const response = await axios.post(
                "http://localhost:8001/generator/ai/eng",
                engagement
            );

            setCaseStudy({ language: "English AI Response", content: response.data });
        } catch (error) {
            console.error("Error creating English AI response:", error);

            if (error.response) {
                setError(
                    `Failed to create English AI response. Status: ${error.response.status}`
                );
            } else {
                setError("Failed to connect to the server.");
            }
        } finally {
            setCreatingEnglishAiResponse(false);
        }
    };

    if (loading) {
        return <div>Loading...</div>;
    }

    if (error && !engagement) {
        return <div>{error}</div>;
    }

    if (!engagement) {
        return <div>Engagement not found.</div>;
    }

    return (
        <div className="engagement-detail-container">

            <div className="engagement-detail-header">
                <h1>Engagement Detail</h1>

                <button
                    className="back-button"
                    onClick={() => navigate("/engagements")}
                    disabled={deleting}
                >
                    Back to Engagements
                </button>

                <button
                    className="edit-button"
                    onClick={() => navigate(`/engagements/${id}/edit`)}
                    disabled={deleting}
                >
                    Edit Engagement
                </button>

                <button
                    className="delete-button"
                    onClick={deleteEngagement}
                    disabled={deleting}
                >
                    {deleting ? "Deleting..." : "Delete Engagement"}
                </button>
            </div>

            <div className="engagement-detail-content">

                <h2>ID: {engagement.id}</h2>

                <p>
                    <strong>Client:</strong> {engagement.client}
                </p>

                <p>
                    <strong>Client Type:</strong>{" "}
                    {engagement.client_type}
                </p>

                <p>
                    <strong>May Be Named:</strong>{" "}
                    {engagement.may_be_named ? "Yes" : "No"}
                </p>

                <p>
                    <strong>Domain:</strong> {engagement.domain}
                </p>

                <p>
                    <strong>Region:</strong> {engagement.region}
                </p>

                <p>
                    <strong>Challenge:</strong>{" "}
                    {engagement.challenge}
                </p>

                <p>
                    <strong>Solution:</strong>{" "}
                    {engagement.solution}
                </p>

                <p>
                    <strong>Technologies:</strong>{" "}
                    {engagement.technologies?.join(", ")}
                </p>

                <p>
                    <strong>Team Size:</strong>{" "}
                    {engagement.team_size}
                </p>

                <p>
                    <strong>Duration (Months):</strong>{" "}
                    {engagement.duration_months}
                </p>

                <h3>Outcomes:</h3>

                <ul>
                    {engagement.outcomes?.map((outcome, index) => (
                        <li key={index}>
                            <p>
                                <strong>Metric:</strong>{" "}
                                {outcome.metric}
                            </p>

                            <p>
                                <strong>Source Reference:</strong>{" "}
                                {outcome.source_ref}
                            </p>
                        </li>
                    ))}
                </ul>

                <div className="case-study-action">
                    <button
                        className="create-case-study-button create-detail-study-button"
                        onClick={() => createCaseStudy("English")}
                        disabled={Boolean(creatingCaseStudy) || creatingEnglishAiResponse || deleting}
                    >
                        {creatingCaseStudy === "English"
                            ? "Creating Case Study..."
                            : "Create Detail Study"}
                    </button>

                    <div className="case-study-secondary-actions">
                        <button
                            className="create-case-study-button"
                            onClick={createEnglishAiResponse}
                            disabled={Boolean(creatingCaseStudy) || creatingEnglishAiResponse || deleting}
                        >
                            {creatingEnglishAiResponse
                                ? "Generating English AI Response..."
                                : "Generate English AI Response"}
                        </button>

                        <button
                            className="create-case-study-button"
                            onClick={() => createCaseStudy("German")}
                            disabled={Boolean(creatingCaseStudy) || creatingEnglishAiResponse || deleting}
                        >
                            {creatingCaseStudy === "German"
                                ? "Generating German MCS..."
                                : "Generate German MCS"}
                        </button>

                        <button
                            className="create-case-study-button"
                            onClick={() => createCaseStudy("Turkish")}
                            disabled={Boolean(creatingCaseStudy) || creatingEnglishAiResponse || deleting}
                        >
                            {creatingCaseStudy === "Turkish"
                                ? "Generating Turkish MCS..."
                                : "Generate Turkish MCS"}
                        </button>
                    </div>
                </div>

                {error && (
                    <div className="case-study-error">
                        {error}
                    </div>
                )}

                {caseStudy && (
                    <div className="case-study-result">
                        <h2>Generated {caseStudy.language} Case Study</h2>

                        <pre>
                            {JSON.stringify(caseStudy.content, null, 2)}
                        </pre>
                    </div>
                )}
            </div>
        </div>
    );
}

export default EngagementDetail;
