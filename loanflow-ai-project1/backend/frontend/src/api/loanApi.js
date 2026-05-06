export async function reviewLoan(payload){
    const response = await fetch("http://127.0.0.1:8000/agent/review",{
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw new Error("Failed to review loan");
  }
  const data = await response.json();   // 👈 THIS LINE IS IMPORTANT
  return data;
}