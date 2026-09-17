import { useState } from "react";
import { publishRecord } from "./api/publisher";

/**
 * Drop-in button that publishes an engagement record via the
 * Publisher service (which internally runs the Verifier gate).
 *
 * Usage in EngagementDetail.jsx:
 *   import PublishButton from "./PublishButton";
 *   ...
 *   <PublishButton recordId={engagement.id} />
 */
function PublishButton({ recordId }) {
    const [publishing, setPublishing] = useState(false);
    const [result, setResult] = useState(null);
    const [error, setError] = useState(null);

    const handlePublish = async () => {
        setPublishing(true);
        setError(null);
        setResult(null);

        try {
            const data = await publishRecord(recordId);
            setResult(data.path);
        } catch (err) {
            console.error("Error publishing record:", err);

            if (err.response) {
                const detail = err.response.data?.detail;

                if (detail && detail.problems) {
                    setError(
                        `Publish blocked by Verifier: ${detail.problems
                            .map((p) => JSON.stringify(p))
                            .join("; ")}`
                    );
                } else {
                    setError(
                        `Failed to publish. Status: ${err.response.status}`
                    );
                }
            } else {
                setError("Failed to connect to the Publisher service.");
            }
        } finally {
            setPublishing(false);
        }
    };

    return (
        <div className="publish-button-container">
            <button
                className="create-case-study-button"
                onClick={handlePublish}
                disabled={publishing}
            >
                {publishing ? "Publishing..." : "Publish Document"}
            </button>

            {error && <div className="case-study-error">{error}</div>}

            {result && (
                <div className="case-study-result">
                    <p>
                        <strong>Document ready:</strong> {result}
                    </p>
                </div>
            )}
        </div>
    );
}

export default PublishButton;