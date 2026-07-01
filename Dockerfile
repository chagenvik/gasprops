FROM python:3.13.9-slim-trixie

WORKDIR /app

# Install Java runtime required by neqsim/JPype.
RUN apt-get update && apt-get install -y --no-install-recommends \
    default-jre-headless \
    && rm -rf /var/lib/apt/lists/*

ENV JAVA_HOME=/usr/lib/jvm/default-java
ENV JAVA_TOOL_OPTIONS="--enable-native-access=ALL-UNNAMED"

RUN pip install --no-cache-dir --upgrade pip

COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY .streamlit/ ./.streamlit/
COPY src/ ./src/
COPY data/ ./data/
COPY assets/ ./assets/
COPY streamlit_app.py ./streamlit_app.py

USER 1001

EXPOSE 8501

ENTRYPOINT ["streamlit", "run", "streamlit_app.py", "--server.address=0.0.0.0", "--server.port=8501"]