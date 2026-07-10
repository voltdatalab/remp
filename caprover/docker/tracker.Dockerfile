FROM golang:1.25-alpine AS build
RUN apk add --no-cache make git build-base
WORKDIR /src
COPY Beam/go/go.mod Beam/go/go.sum ./
RUN go mod download
COPY Beam/go ./
WORKDIR /src/cmd/tracker
RUN make build-static

FROM alpine:3.22
RUN apk add --no-cache ca-certificates openssl tzdata
WORKDIR /bin
COPY --from=build /src/cmd/tracker/tracker /bin/tracker
COPY Beam/go/cmd/tracker/.env.example /bin/.env.example
# The binary requires a .env file at startup. CapRover environment variables
# override these example defaults, so secrets remain outside the image.
COPY Beam/go/cmd/tracker/.env.example /bin/.env
EXPOSE 8081
CMD ["/bin/tracker"]
