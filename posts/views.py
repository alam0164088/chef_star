from django.http import HttpResponse


def create_post(request):
    return HttpResponse('Create post (placeholder)')


def like_post(request, post_id):
    return HttpResponse(f'Like post {post_id} (placeholder)')


def comment_post(request, post_id):
    return HttpResponse(f'Comment on post {post_id} (placeholder)')
