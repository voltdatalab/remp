FROM golang:1.25-alpine AS build
RUN apk add --no-cache make git build-base
WORKDIR /src
COPY Beam/go/go.mod Beam/go/go.sum ./
RUN go mod download
COPY Beam/go ./
WORKDIR /src/cmd/segments
RUN make build-static

FROM alpine:3.22
RUN apk add --no-cache ca-certificates openssl tzdata
WORKDIR /bin
COPY --from=build /src/cmd/segments/segments /bin/segments
COPY Beam/go/cmd/segments/.env.example /bin/.env.example
EXPOSE 8082
CMD ["/bin/segments"]
