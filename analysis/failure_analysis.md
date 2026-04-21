# Báo cáo Phân tích Thất bại (Failure Analysis Report)

## 1. Tổng quan Benchmark
- **Tổng số cases:** 50
- **Chế độ chạy:** online
- **Tỉ lệ Pass/Fail:** 50/0
- **Điểm RAGAS trung bình:**
    - Faithfulness: 0.82
    - Relevancy: 0.58
- **Điểm LLM-Judge trung bình:** 4.91 / 5.0

## 2. Phân nhóm lỗi (Failure Clustering)
| Nhóm lỗi | Số lượng | Nguyên nhân dự kiến |
|----------|----------|---------------------|
| Hallucination | 0 | Retriever lấy thiếu context hoặc context không đủ rõ |
| Incomplete | 0 | Agent từ chối trả lời hoặc thiếu thông tin chi tiết |
| Tone Mismatch | 0 | Câu trả lời chưa đúng mức độ chuyên nghiệp mong muốn |

## 3. Phân tích 5 Whys (Risk-based, vì không có fail case)
### Case #1: Relevancy vẫn thấp hơn kỳ vọng (0.58)
1. **Symptom:** Một số câu trả lời đúng thông tin nhưng chưa bám sát ý hỏi.
2. **Why 1:** Agent ưu tiên tổng hợp context, đôi khi thêm thông tin phụ.
3. **Why 2:** Prompt chưa ép định dạng "trả lời trực tiếp theo intent trước".
4. **Why 3:** Retrieval hiện dựa nhiều vào token overlap và synonym map đơn giản.
5. **Why 4:** Chưa có semantic reranker sau top-k ban đầu.
6. **Root Cause:** Chất lượng retrieval + answer-format control chưa tối ưu cho câu hỏi paraphrase/ambiguous.

### Case #2: Latency online tăng đáng kể so với baseline
1. **Symptom:** Delta latency +1.16s khi bật online judge/agent.
2. **Why 1:** Candidate mode gọi OpenAI cho generation và 2 judge models.
3. **Why 2:** Mỗi case có nhiều network round-trips.
4. **Why 3:** Chưa có cache cho các prompt judge trùng pattern.
5. **Why 4:** Chưa có cơ chế adaptive judge (chỉ gọi judge thứ 2 khi score biên).
6. **Root Cause:** Thiết kế ưu tiên quality trước cost/latency.

## 4. Kế hoạch cải tiến (Action Plan)
- [ ] Thêm semantic reranker sau retrieval ban đầu để tăng relevancy trên câu hỏi paraphrase.
- [ ] Bổ sung answer template theo thứ tự: direct answer -> evidence -> caveat.
- [ ] Chạy adaptive judging: nếu judge A >= 4.7 thì bỏ qua judge B để giảm chi phí.
- [ ] Caching kết quả judge cho các case trùng cấu trúc prompt.
- [ ] Theo dõi thêm P95 latency và cost/case ở release gate.
