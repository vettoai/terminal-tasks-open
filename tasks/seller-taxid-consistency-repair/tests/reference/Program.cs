using SellerRegistration;

var builder = WebApplication.CreateBuilder(args);
builder.Configuration.AddJsonFile("appsettings.Development.json", optional: true).AddEnvironmentVariables();
builder.Services.AddSingleton<ProfileRepository>();
builder.Services.AddSingleton<ProfileWriter>();
var app = builder.Build();

Integration? Caller(HttpRequest request) =>
    app.Configuration.GetSection("Integrations").Get<List<Integration>>()?
        .FirstOrDefault(item => request.Headers.Authorization == "Bearer " + item.Token);

app.MapGet("/health", async (ProfileRepository repository) =>
    await repository.Healthy() ? Results.Ok(new { status = "ok" }) : Results.StatusCode(503));

app.MapPost("/api/partner/sellers", async (HttpRequest request, ProfileRequest body, ProfileWriter writer) =>
{
    var caller = Caller(request);
    if (caller is null) return Results.Unauthorized();
    if (body.PersonType == "F") body.ContactTaxId = body.AccountTaxId;
    return Results.Ok(await writer.Signup(body, caller));
});

app.MapPut("/api/partner/sellers/{id}", async (string id, HttpRequest request, ProfileRequest body, ProfileWriter writer) =>
{
    var caller = Caller(request);
    if (caller is null) return Results.Unauthorized();
    return Results.Ok(await writer.Save(id, body, caller, true));
});

app.MapPost("/internal/dashboard/seller/{id}/profile", async (string id, HttpRequest request, ProfileRequest body, ProfileWriter writer) =>
{
    var caller = Caller(request);
    if (caller is null || caller.Kind != "first-party") return Results.Unauthorized();
    if (body.PersonType == "F") body.AccountTaxId = body.ContactTaxId;
    return Results.Ok(await writer.Save(id, body, caller, false));
});
app.Run();
