#include <Arduino.h>
#include <esp_system.h>
#include <math.h>

namespace {

constexpr int MODEM_TX_PIN = 4;
constexpr int MODEM_RX_PIN = 5;
constexpr int MODEM_DTR_PIN = 7;
constexpr int MODEM_PWRKEY_PIN = 46;
constexpr int BOARD_POWER_SAVE_MODE_PIN = 42;
constexpr int BATTERY_ADC_PIN = 8;

constexpr uint32_t MODEM_BAUD = 115200;
constexpr char APN[] = "iotde.telefonica.com";
constexpr char SERVER_HOSTNAME[] = "sailtracker.wyraz.de";
constexpr uint16_t SERVER_PORT = 39001;
constexpr uint16_t LOCAL_UDP_PORT = 39000;
constexpr uint32_t POSITION_INTERVAL_MS = 1000;
constexpr uint32_t STATUS_INTERVAL_MS = 10000;
constexpr uint32_t FIX_FRESH_MS = 3000;
constexpr unsigned BATTERY_SAMPLE_COUNT = 32;
constexpr size_t POSITION_PACKET_SIZE = 26;
constexpr size_t STATUS_PACKET_SIZE = 58;
constexpr size_t MAX_COAP_DATAGRAM_SIZE = 96;

constexpr uint8_t PACKET_TYPE_POSITION = 1;
constexpr uint8_t PACKET_TYPE_STATUS = 2;
constexpr uint16_t UNKNOWN_U16 = UINT16_MAX;
constexpr int8_t UNKNOWN_I8 = INT8_MIN;
constexpr int16_t UNKNOWN_I16 = INT16_MIN;
constexpr uint8_t UNKNOWN_U8 = UINT8_MAX;
constexpr uint8_t CELL_STATE_DATA = 3;

constexpr uint16_t FLAG_POSITION_KNOWN = 1U << 0;
constexpr uint16_t FLAG_FIX_CURRENT = 1U << 1;
constexpr uint16_t FLAG_GNSS_ON = 1U << 2;
constexpr uint16_t FLAG_GNSS_ERROR = 1U << 3;
constexpr int32_t UNKNOWN_COORDINATE = INT32_MIN;

HardwareSerial SerialAT(1);

String serverIp;
uint32_t deviceId = 0;
uint32_t bootId = 0;
uint32_t sequenceNumber = 0;
bool udpSocketReady = false;
bool gnssOn = false;
bool gnssError = false;
bool havePosition = false;
int32_t latitudeE7 = UNKNOWN_COORDINATE;
int32_t longitudeE7 = UNKNOWN_COORDINATE;
uint32_t lastFixMs = 0;
uint32_t nextPositionMs = 0;
uint32_t nextStatusMs = 0;
uint16_t coapMessageId = 0;
uint16_t batteryMv = UNKNOWN_U16;
uint16_t batteryMinMv = UNKNOWN_U16;
uint16_t speedCms = UNKNOWN_U16;
uint16_t courseCdeg = UNKNOWN_U16;
uint16_t hdopX100 = UNKNOWN_U16;
uint8_t satellites = UNKNOWN_U8;
int8_t rssiDbm = UNKNOWN_I8;

String readModem(uint32_t timeoutMs, bool stopAtPrompt = false)
{
    String response;
    response.reserve(512);
    const uint32_t start = millis();
    uint32_t lastByte = start;

    while (millis() - start < timeoutMs) {
        bool received = false;
        while (SerialAT.available()) {
            const char c = static_cast<char>(SerialAT.read());
            response += c;
            lastByte = millis();
            received = true;
            if (stopAtPrompt && c == '>') {
                return response;
            }
        }

        if (!received && millis() - lastByte > 200 &&
            (response.indexOf("\r\nOK\r\n") >= 0 ||
             response.indexOf("\r\nERROR\r\n") >= 0)) {
            break;
        }
        delay(10);
    }
    return response;
}

String atCommand(const String &command, uint32_t timeoutMs = 2000)
{
    while (SerialAT.available()) {
        SerialAT.read();
    }
    SerialAT.print(command);
    SerialAT.print('\r');
    SerialAT.flush();
    String response = readModem(timeoutMs);
    Serial.printf("[AT] %s\n%s\n", command.c_str(), response.c_str());
    return response;
}

bool modemResponds()
{
    for (int attempt = 0; attempt < 3; ++attempt) {
        if (atCommand("AT", 1000).indexOf("OK") >= 0) {
            return true;
        }
        delay(300);
    }
    return false;
}

bool startModem()
{
    pinMode(BOARD_POWER_SAVE_MODE_PIN, OUTPUT);
    digitalWrite(BOARD_POWER_SAVE_MODE_PIN, HIGH);

    pinMode(MODEM_DTR_PIN, OUTPUT);
    digitalWrite(MODEM_DTR_PIN, LOW);

    if (modemResponds()) {
        return true;
    }

    Serial.println("Modem is not responding; running the PWRKEY sequence.");
    pinMode(MODEM_PWRKEY_PIN, OUTPUT);
    digitalWrite(MODEM_PWRKEY_PIN, LOW);
    delay(100);
    digitalWrite(MODEM_PWRKEY_PIN, HIGH);
    delay(100);
    digitalWrite(MODEM_PWRKEY_PIN, LOW);

    for (int attempt = 0; attempt < 30; ++attempt) {
        delay(500);
        if (modemResponds()) {
            return true;
        }
    }
    return false;
}

int registrationState(const String &response)
{
    const int marker = response.indexOf("+CEREG:");
    if (marker < 0) {
        return -1;
    }
    const int end = response.indexOf('\n', marker);
    String line = response.substring(marker + 7, end < 0 ? response.length() : end);
    line.trim();
    const int comma = line.indexOf(',');
    if (comma >= 0) {
        line = line.substring(comma + 1);
    }
    return line.toInt();
}

bool waitForNetwork()
{
    atCommand("AT+CPIN?", 2000);
    atCommand("AT+CTZU=1", 2000);
    atCommand(String("AT+CGDCONT=1,\"IP\",\"") + APN + "\"", 3000);

    for (int attempt = 0; attempt < 90; ++attempt) {
        const String response = atCommand("AT+CEREG?", 1500);
        const int state = registrationState(response);
        if (state == 1 || state == 5) {
            Serial.printf("LTE registered (CEREG=%d).\n", state);
            return true;
        }
        delay(1000);
    }
    return false;
}

bool openNetworkService()
{
    String response = atCommand("AT+NETOPEN?", 2000);
    if (response.indexOf("+NETOPEN: 1") >= 0) {
        return true;
    }

    atCommand("AT+NETOPEN", 12000);
    for (int attempt = 0; attempt < 10; ++attempt) {
        response = atCommand("AT+NETOPEN?", 2000);
        if (response.indexOf("+NETOPEN: 1") >= 0) {
            return true;
        }
        delay(1000);
    }
    return false;
}

bool openUdpSocket()
{
    atCommand("AT+CIPCLOSE=0", 3000);
    const String command = String("AT+CIPOPEN=0,\"UDP\",,,") + LOCAL_UDP_PORT;
    const String response = atCommand(command, 5000);
    udpSocketReady = response.indexOf("+CIPOPEN: 0,0") >= 0;
    return udpSocketReady;
}

bool isValidIpv4Address(const String &address)
{
    int octets = 0;
    int value = 0;
    int digits = 0;
    for (size_t index = 0; index <= address.length(); ++index) {
        const char character = index < address.length() ? address[index] : '.';
        if (character >= '0' && character <= '9') {
            value = value * 10 + character - '0';
            if (++digits > 3 || value > 255) {
                return false;
            }
            continue;
        }
        if (character != '.' || digits == 0 || ++octets > 4) {
            return false;
        }
        value = 0;
        digits = 0;
    }
    return octets == 4;
}

bool resolveServerAddress()
{
    const String response = atCommand(String("AT+CDNSGIP=\"") + SERVER_HOSTNAME + "\"", 30000);
    const int marker = response.indexOf("+CDNSGIP: 1,");
    if (marker < 0) {
        Serial.printf("Could not resolve %s.\n", SERVER_HOSTNAME);
        return false;
    }

    const int hostnameStart = response.indexOf('"', marker);
    const int hostnameEnd = response.indexOf('"', hostnameStart + 1);
    const int addressStart = response.indexOf('"', hostnameEnd + 1);
    const int addressEnd = response.indexOf('"', addressStart + 1);
    if (hostnameStart < 0 || hostnameEnd < 0 || addressStart < 0 || addressEnd < 0) {
        Serial.println("DNS response has an unexpected format.");
        return false;
    }

    const String resolvedAddress = response.substring(addressStart + 1, addressEnd);
    if (!isValidIpv4Address(resolvedAddress)) {
        Serial.println("DNS response does not contain a valid IPv4 address.");
        return false;
    }

    serverIp = resolvedAddress;
    Serial.printf("Resolved %s to %s.\n", SERVER_HOSTNAME, serverIp.c_str());
    return true;
}

bool ensureUdpSocket()
{
    if (udpSocketReady) {
        return true;
    }
    if (!openNetworkService()) {
        Serial.println("Could not open the modem network service.");
        return false;
    }
    if (!openUdpSocket()) {
        Serial.println("Could not open the UDP socket.");
        return false;
    }
    return true;
}

bool enableGnss()
{
    const bool gpioDirection = atCommand("AT+CGDRT=1,1", 2000).indexOf("OK") >= 0;
    const bool antennaPower = atCommand("AT+CGSETV=1,1", 2000).indexOf("OK") >= 0;
    const bool gnssPower = atCommand("AT+CGNSSPWR=1", 10000).indexOf("OK") >= 0;
    gnssOn = gpioDirection && antennaPower && gnssPower;
    gnssError = !gnssOn;
    return gnssOn;
}

bool parseDecimalCoordinate(const String &value, const String &hemisphere, bool latitude, int32_t &result)
{
    if (value.isEmpty() || hemisphere.isEmpty()) {
        return false;
    }
    double decimal = value.toDouble();
    if (hemisphere == "S" || hemisphere == "W") {
        decimal = -decimal;
    }
    const double limit = latitude ? 90.0 : 180.0;
    if (decimal < -limit || decimal > limit) {
        return false;
    }
    result = static_cast<int32_t>(llround(decimal * 10000000.0));
    return true;
}

bool updatePosition()
{
    const String response = atCommand("AT+CGNSSINFO", 2500);
    constexpr char RESPONSE_PREFIX[] = "+CGNSSINFO:";
    const int marker = response.indexOf(RESPONSE_PREFIX);
    if (marker < 0) {
        gnssError = true;
        return false;
    }

    int end = response.indexOf('\n', marker);
    String body = response.substring(marker + strlen(RESPONSE_PREFIX),
                                     end < 0 ? response.length() : end);
    body.trim();

    String field[18];
    int fieldIndex = 0;
    int start = 0;
    while (fieldIndex < 18) {
        const int comma = body.indexOf(',', start);
        if (comma < 0) {
            field[fieldIndex++] = body.substring(start);
            break;
        }
        field[fieldIndex++] = body.substring(start, comma);
        start = comma + 1;
    }

    int32_t newLatitude = 0;
    int32_t newLongitude = 0;
    if (!parseDecimalCoordinate(field[5], field[6], true, newLatitude) ||
        !parseDecimalCoordinate(field[7], field[8], false, newLongitude)) {
        gnssError = false;
        speedCms = UNKNOWN_U16;
        courseCdeg = UNKNOWN_U16;
        hdopX100 = UNKNOWN_U16;
        satellites = UNKNOWN_U8;
        return false;
    }

    latitudeE7 = newLatitude;
    longitudeE7 = newLongitude;
    havePosition = true;
    lastFixMs = millis();
    gnssError = false;
    const double speedKnots = field[12].toDouble();
    const double courseDegrees = field[13].toDouble();
    const double hdop = field[15].toDouble();
    speedCms = field[12].isEmpty() ? UNKNOWN_U16 : static_cast<uint16_t>(min(65534.0, round(speedKnots * 51.444444)));
    courseCdeg = field[13].isEmpty() || courseDegrees < 0.0 || courseDegrees >= 360.0
                     ? UNKNOWN_U16
                     : static_cast<uint16_t>(round(courseDegrees * 100.0));
    hdopX100 = field[15].isEmpty() ? UNKNOWN_U16 : static_cast<uint16_t>(min(65534.0, round(hdop * 100.0)));
    satellites = field[17].isEmpty() ? UNKNOWN_U8 : static_cast<uint8_t>(min(254L, field[17].toInt()));
    Serial.printf("GNSS fix: %.7f, %.7f speed=%u cm/s course=%u cdeg sats=%u hdop=%u\n",
                  latitudeE7 / 1e7, longitudeE7 / 1e7, speedCms, courseCdeg, satellites, hdopX100);
    return true;
}

void updateSignalQuality()
{
    const String response = atCommand("AT+CSQ", 2000);
    const int marker = response.indexOf("+CSQ:");
    if (marker < 0) {
        rssiDbm = UNKNOWN_I8;
        return;
    }
    String value = response.substring(marker + 5, response.indexOf(',', marker));
    value.trim();
    const int csq = value.toInt();
    rssiDbm = csq >= 0 && csq <= 31 ? static_cast<int8_t>(-113 + 2 * csq) : UNKNOWN_I8;
}

uint16_t readBatteryAdcMv()
{
    uint32_t sumMv = 0;
    for (unsigned sample = 0; sample < BATTERY_SAMPLE_COUNT; ++sample) {
        sumMv += analogReadMilliVolts(BATTERY_ADC_PIN);
        delay(2);
    }
    const uint32_t voltageMv = (sumMv / BATTERY_SAMPLE_COUNT) * 2U;
    return voltageMv >= 2500U && voltageMv <= 5000U
               ? static_cast<uint16_t>(voltageMv)
               : UNKNOWN_U16;
}

uint16_t readModemBatteryMv()
{
    const String response = atCommand("AT+CBC", 3000);
    const int marker = response.indexOf("+CBC:");
    const int unit = response.indexOf('V', marker);
    if (marker < 0 || unit < 0) {
        return UNKNOWN_U16;
    }
    String voltage = response.substring(marker + 5, unit);
    voltage.trim();
    const uint32_t voltageMv = static_cast<uint32_t>(lround(voltage.toFloat() * 1000.0F));
    return voltageMv >= 2500U && voltageMv <= 5000U
               ? static_cast<uint16_t>(voltageMv)
               : UNKNOWN_U16;
}

void updateBatteryVoltage(bool queryModem)
{
    const uint16_t adcMv = readBatteryAdcMv();
    const uint16_t modemMv = queryModem ? readModemBatteryMv() : UNKNOWN_U16;
    batteryMv = adcMv != UNKNOWN_U16 ? adcMv : modemMv;
    if (batteryMv != UNKNOWN_U16 &&
        (batteryMinMv == UNKNOWN_U16 || batteryMv < batteryMinMv)) {
        batteryMinMv = batteryMv;
    }
    Serial.printf("Battery ADC=%s modem=%s selected=%s mV\n",
                  adcMv == UNKNOWN_U16 ? "unknown" : String(adcMv).c_str(),
                  modemMv == UNKNOWN_U16 ? "unknown" : String(modemMv).c_str(),
                  batteryMv == UNKNOWN_U16 ? "unknown" : String(batteryMv).c_str());
}

void putU16(uint8_t *buffer, size_t offset, uint16_t value)
{
    buffer[offset] = static_cast<uint8_t>(value >> 8);
    buffer[offset + 1] = static_cast<uint8_t>(value);
}

void putU32(uint8_t *buffer, size_t offset, uint32_t value)
{
    buffer[offset] = static_cast<uint8_t>(value >> 24);
    buffer[offset + 1] = static_cast<uint8_t>(value >> 16);
    buffer[offset + 2] = static_cast<uint8_t>(value >> 8);
    buffer[offset + 3] = static_cast<uint8_t>(value);
}

uint16_t currentPositionFlags()
{
    uint16_t flags = 0;
    if (havePosition) {
        flags |= FLAG_POSITION_KNOWN;
        if (millis() - lastFixMs <= FIX_FRESH_MS) {
            flags |= FLAG_FIX_CURRENT;
        }
    }
    if (gnssOn) {
        flags |= FLAG_GNSS_ON;
    }
    if (gnssError) {
        flags |= FLAG_GNSS_ERROR;
    }
    return flags;
}

void buildHeader(uint8_t *packet, uint8_t packetType, uint32_t sequence)
{
    packet[0] = 'O';
    packet[1] = 'S';
    packet[2] = 1;
    packet[3] = packetType;
    putU32(packet, 4, deviceId);
    putU32(packet, 8, bootId);
    putU32(packet, 12, sequence);
}

void buildPositionPacket(uint8_t (&packet)[POSITION_PACKET_SIZE], uint32_t sequence)
{
    memset(packet, 0, sizeof(packet));
    buildHeader(packet, PACKET_TYPE_POSITION, sequence);
    putU16(packet, 16, currentPositionFlags());
    putU32(packet, 18, static_cast<uint32_t>(havePosition ? latitudeE7 : UNKNOWN_COORDINATE));
    putU32(packet, 22, static_cast<uint32_t>(havePosition ? longitudeE7 : UNKNOWN_COORDINATE));
}

void buildStatusPacket(uint8_t (&packet)[STATUS_PACKET_SIZE], uint32_t sequence)
{
    memset(packet, 0, sizeof(packet));
    buildHeader(packet, PACKET_TYPE_STATUS, sequence);
    putU16(packet, 16, currentPositionFlags());
    putU32(packet, 18, static_cast<uint32_t>(havePosition ? latitudeE7 : UNKNOWN_COORDINATE));
    putU32(packet, 22, static_cast<uint32_t>(havePosition ? longitudeE7 : UNKNOWN_COORDINATE));
    putU32(packet, 26, millis() / 1000U);
    putU16(packet, 30, batteryMv);
    putU16(packet, 32, batteryMinMv);
    const uint32_t fixAgeMs = havePosition ? millis() - lastFixMs : UNKNOWN_U16;
    putU16(packet, 34, static_cast<uint16_t>(min(fixAgeMs, static_cast<uint32_t>(UNKNOWN_U16))));
    putU16(packet, 36, speedCms);
    putU16(packet, 38, courseCdeg);
    packet[40] = satellites;
    putU16(packet, 41, hdopX100);
    packet[43] = CELL_STATE_DATA;
    packet[44] = static_cast<uint8_t>(rssiDbm);
    putU16(packet, 45, static_cast<uint16_t>(UNKNOWN_I16));
    putU16(packet, 47, static_cast<uint16_t>(UNKNOWN_I16));
    putU16(packet, 49, static_cast<uint16_t>(UNKNOWN_I16));
    putU32(packet, 51, 0);
    putU16(packet, 55, 0);
    packet[57] = static_cast<uint8_t>(esp_reset_reason());
}

bool sendUdp(const uint8_t *payload, size_t length)
{
    if (!ensureUdpSocket()) {
        return false;
    }
    if (serverIp.isEmpty() && !resolveServerAddress()) {
        return false;
    }

    while (SerialAT.available()) {
        SerialAT.read();
    }
    const String command = String("AT+CIPSEND=0,") + length + ",\"" + serverIp + "\"," + SERVER_PORT;
    SerialAT.print(command);
    SerialAT.print('\r');
    SerialAT.flush();
    String response = readModem(3000, true);
    Serial.printf("[AT] %s\n%s\n", command.c_str(), response.c_str());
    if (response.indexOf('>') < 0) {
        udpSocketReady = false;
        serverIp = "";
        return false;
    }

    SerialAT.write(payload, length);
    SerialAT.flush();
    response = readModem(8000);
    Serial.printf("[UDP] %s\n", response.c_str());
    const String expected = String("+CIPSEND: 0,") + length + "," + length;
    if (response.indexOf(expected) < 0) {
        udpSocketReady = false;
        serverIp = "";
        return false;
    }
    return true;
}

bool sendCoapPost(const char *resource, bool confirmable, const uint8_t *payload, size_t payloadLength)
{
    const size_t resourceLength = strlen(resource);
    if (resourceLength > 12 || payloadLength + resourceLength + 12 > MAX_COAP_DATAGRAM_SIZE) {
        return false;
    }

    uint8_t datagram[MAX_COAP_DATAGRAM_SIZE];
    size_t offset = 0;
    datagram[offset++] = confirmable ? 0x40 : 0x50;
    datagram[offset++] = 0x02;
    putU16(datagram, offset, coapMessageId++);
    offset += 2;

    datagram[offset++] = 0xB2;
    datagram[offset++] = 'v';
    datagram[offset++] = '1';
    datagram[offset++] = static_cast<uint8_t>(resourceLength);
    memcpy(datagram + offset, resource, resourceLength);
    offset += resourceLength;
    datagram[offset++] = 0x11;
    datagram[offset++] = 42;
    datagram[offset++] = 0xFF;
    memcpy(datagram + offset, payload, payloadLength);
    offset += payloadLength;
    return sendUdp(datagram, offset);
}

} // namespace

void setup()
{
    Serial.begin(115200);
    delay(1500);
    Serial.println("\nOpen Sail Tracker CoAP PoC starting.");

    const uint64_t mac = ESP.getEfuseMac();
    deviceId = static_cast<uint32_t>(mac ^ (mac >> 32));
    bootId = esp_random();
    Serial.printf("device_id=%08lX boot_id=%08lX\n",
                  static_cast<unsigned long>(deviceId),
                  static_cast<unsigned long>(bootId));

    SerialAT.begin(MODEM_BAUD, SERIAL_8N1, MODEM_RX_PIN, MODEM_TX_PIN);
    if (!startModem()) {
        Serial.println("FATAL: Modem is not responding.");
        return;
    }

    atCommand("ATE0", 1000);
    if (!waitForNetwork()) {
        Serial.println("WARNING: Not registered with LTE yet.");
    }
    analogSetAttenuation(ADC_11db);
    analogReadResolution(12);
    enableGnss();
    if (ensureUdpSocket()) {
        resolveServerAddress();
    }
    coapMessageId = static_cast<uint16_t>(esp_random());
    nextPositionMs = millis();
    nextStatusMs = millis();
}

void loop()
{
    const uint32_t now = millis();
    const bool positionDue = static_cast<int32_t>(now - nextPositionMs) >= 0;
    const bool statusDue = static_cast<int32_t>(now - nextStatusMs) >= 0;
    if (!positionDue && !statusDue) {
        delay(10);
        return;
    }

    updatePosition();
    updateBatteryVoltage(statusDue);
    if (statusDue) {
        updateSignalQuality();
    }

    if (positionDue) {
        nextPositionMs = now + POSITION_INTERVAL_MS;
        uint8_t packet[POSITION_PACKET_SIZE];
        const uint32_t packetSequence = sequenceNumber++;
        buildPositionPacket(packet, packetSequence);
        const bool sent = sendCoapPost("position", false, packet, sizeof(packet));
        Serial.printf("Position seq=%lu %s (%ld, %ld)\n",
                      static_cast<unsigned long>(packetSequence),
                      sent ? "sent" : "FAILED",
                      static_cast<long>(latitudeE7),
                      static_cast<long>(longitudeE7));
    }

    if (statusDue) {
        nextStatusMs = now + STATUS_INTERVAL_MS;
        uint8_t packet[STATUS_PACKET_SIZE];
        const uint32_t packetSequence = sequenceNumber++;
        buildStatusPacket(packet, packetSequence);
        const bool sent = sendCoapPost("status", true, packet, sizeof(packet));
        Serial.printf("Status seq=%lu %s\n",
                      static_cast<unsigned long>(packetSequence),
                      sent ? "sent" : "FAILED");
        if (sent) {
            batteryMinMv = batteryMv;
        }
    }
}
